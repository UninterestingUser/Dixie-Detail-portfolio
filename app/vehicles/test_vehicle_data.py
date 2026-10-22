"""The vehicle data import, on small fixture files in the download cache's
layout. No test touches the network: every file is already in the cache, and
the opener given to the fetcher fails the test if it is ever called."""

import datetime
import io
import shutil
import tempfile
import urllib.error
import zipfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from vehicles.models import VehicleDataImportRun, VehicleModel, VehicleModelYear
from vehicles.vehicle_data import canada
from vehicles.vehicle_data.config import Config, QueryMake, load_config
from vehicles.vehicle_data.fetch import FetchError, Fetcher
from vehicles.vehicle_data.names import Names
from vehicles.vehicle_data.run import run

FIXTURES = Path(__file__).parent / "test_files" / "vehicle_data"
Source = VehicleModelYear.Source

CONFIG = Config(
    epa_url="https://epa.invalid/vehicles.csv.zip",
    vpic_url="https://vpic.invalid/api/vehicles/",
    canada_url="https://vpic.invalid/api/vehicles/",
    year_from=2019,
    year_to=2019,
    pause_seconds=1,
    retries=2,
    backoff_seconds=5,
    truck_vehicle_types=("truck", "multipurpose passenger vehicle (mpv)"),
    truck_makes=(QueryMake("Ford", frozenset({"FORD"})),),
    motorcycle_makes=(QueryMake("Harley-Davidson", frozenset({"HARLEY-DAVIDSON"})),),
    canada_units="US",
)


def no_network(request, timeout=None):
    raise AssertionError(f"the test tried to download {request.full_url}")


def write_epa_zip(cache, csv_text):
    path = cache / "epa" / "vehicles.csv.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("vehicles.csv", csv_text)


class CachedFixtures:
    """A download cache filled with the fixture files."""

    def setUp(self):
        super().setUp()
        self.cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.cache)
        shutil.copytree(FIXTURES / "vpic", self.cache / "vpic")
        shutil.copytree(FIXTURES / "canada", self.cache / "canada")
        self.epa_csv = (FIXTURES / "epa" / "vehicles.csv").read_text()
        write_epa_zip(self.cache, self.epa_csv)

    def run_import(self, sources=("epa", "vpic", "canada"), dry_run=False):
        fetcher = Fetcher(self.cache, opener=no_network, sleep=lambda seconds: None)
        reports = run(sources, dry_run=dry_run, fetcher=fetcher, config=CONFIG)
        return {report.source: report for report in reports}


def model(make, name, vehicle_type=VehicleModel.VehicleType.VEHICLE):
    return VehicleModel.objects.get(make=make, model=name, vehicle_type=vehicle_type)


def facts(make, name, source, year=2019):
    return VehicleModelYear.objects.get(vehicle_model=model(make, name), year=year, source=source)


class EpaImportTests(CachedFixtures, TestCase):
    def test_one_model_per_base_model_with_ranges_across_its_rows(self):
        report = self.run_import(["epa"])["epa"]
        self.assertEqual(report.result, "succeeded")
        self.assertEqual(report.counts["models added"], 4)
        self.assertEqual(report.counts["model years added"], 4)
        rav4 = facts("Toyota", "RAV4", Source.EPA)
        self.assertEqual(rav4.epa_size_classes, ["Small Sport Utility Vehicle 2WD", "Small Sport Utility Vehicle 4WD"])
        self.assertEqual(rav4.drives, ["All-Wheel Drive", "Front-Wheel Drive"])
        self.assertEqual(rav4.source_ids, [41122, 41126, 41307])
        camry = facts("Toyota", "Camry", Source.EPA)
        self.assertEqual((camry.passenger_volume_min, camry.passenger_volume_max), (100, 100))
        self.assertEqual((camry.luggage_volume_min, camry.luggage_volume_max), (14, 15))
        self.assertEqual(model("Toyota", "RAV4").source, VehicleModel.Source.EPA)
        self.assertEqual((model("Toyota", "RAV4").year_from, model("Toyota", "RAV4").year_to), (2019, 2019))

    def test_body_styles_come_from_the_nonzero_volumes(self):
        self.run_import(["epa"])
        self.assertEqual(facts("Honda", "Civic", Source.EPA).body_styles, ["two-door", "four-door", "hatchback"])
        self.assertEqual(facts("Toyota", "Camry", Source.EPA).body_styles, ["four-door"])
        # All zero, as for pickups, vans and most SUVs.
        self.assertEqual(facts("Toyota", "RAV4", Source.EPA).body_styles, ["unknown"])
        self.assertEqual(facts("Ford", "F150", Source.EPA).body_styles, ["unknown"])

    def test_rows_without_a_year_are_rejected_and_other_years_skipped(self):
        report = self.run_import(["epa"])["epa"]
        self.assertEqual(len(report.rejected), 1)
        self.assertIn("id 39999", report.rejected[0])
        self.assertEqual(report.counts["EPA rows outside the model years, skipped"], 1)
        self.assertFalse(VehicleModelYear.objects.filter(year=2018).exists())

    def test_a_rerun_changes_nothing_and_a_changed_row_is_counted(self):
        self.run_import(["epa"])
        first_seen = facts("Toyota", "Camry", Source.EPA).first_seen
        report = self.run_import(["epa"])["epa"]
        self.assertEqual(report.counts["models added"], 0)
        self.assertEqual(report.counts["model years unchanged"], 4)
        self.assertEqual(report.counts["models unchanged"], 4)

        write_epa_zip(self.cache, self.epa_csv.replace("40720,2019,Toyota,Camry Hybrid LE,Camry,Midsize Cars,Front-Wheel Drive,0,0,100,15",
                                                       "40720,2019,Toyota,Camry Hybrid LE,Camry,Midsize Cars,Front-Wheel Drive,0,0,100,16"))
        report = self.run_import(["epa"])["epa"]
        self.assertEqual(report.counts["model years changed"], 1)
        self.assertEqual(report.counts["models changed"], 1)
        camry = facts("Toyota", "Camry", Source.EPA)
        self.assertEqual(camry.luggage_volume_max, 16)
        self.assertEqual(camry.first_seen, first_seen)
        self.assertGreater(camry.last_seen, first_seen)


class VpicImportTests(CachedFixtures, TestCase):
    def test_gap_fill_adds_only_what_the_epa_leaves_out(self):
        reports = self.run_import(["epa", "vpic"])
        report = reports["vpic"]
        # F-150 is the EPA's F150, so it gets vPIC's facts but no new model.
        self.assertEqual(VehicleModel.objects.filter(make="Ford").count(), 5)
        f150 = facts("Ford", "F150", Source.VPIC)
        self.assertEqual(f150.source_ids, [{"make_id": 460, "model_id": 1801}])
        self.assertEqual(model("Ford", "F-250").source, VehicleModel.Source.NHTSA)
        self.assertEqual(report.counts["models added"], 6)
        self.assertEqual(report.counts["models changed"], 1)
        self.assertIn("Ford F-250 (2019-2019)", report.added_models)

    def test_a_model_listed_as_truck_and_mpv_is_one_model(self):
        self.run_import(["vpic"])
        transit = facts("Ford", "Transit", Source.VPIC)
        self.assertEqual(transit.source_vehicle_types, ["Multipurpose Passenger Vehicle (MPV)", "Truck"])
        self.assertEqual(transit.source_ids, [{"make_id": 460, "model_id": 3608}])

    def test_motorcycles_are_marked_and_other_vpic_makes_rejected(self):
        report = self.run_import(["vpic"])["vpic"]
        model("Harley-Davidson", "Fat Boy", VehicleModel.VehicleType.MOTORCYCLE)  # found as a motorcycle
        self.assertIn("Harley-Davidson Fat Boy (2019-2019, motorcycle)", report.added_models)
        self.assertFalse(VehicleModel.objects.filter(model="Sample Chopper").exists())
        self.assertEqual(len(report.rejected), 1)
        self.assertIn("HARLEY-DAVIDSON CUSTOM SAMPLE", report.rejected[0])


class CanadaImportTests(CachedFixtures, TestCase):
    def test_specifications_attach_to_matching_models_as_ranges(self):
        report = self.run_import()["canada"]
        self.assertEqual(report.result, "succeeded")
        rav4 = facts("Toyota", "RAV4", Source.CANADA)
        self.assertEqual((rav4.curb_weight_min, rav4.curb_weight_max), (3370, 3490))
        self.assertEqual((rav4.height_min, rav4.height_max), (Decimal("66.9"), Decimal("67.0")))
        self.assertEqual((rav4.length_min, rav4.wheelbase_max), (Decimal("180.7"), Decimal("105.9")))
        self.assertEqual(rav4.source_ids, ["RAV4 AWD LE / XLE 4DR SUV", "RAV4 FWD LE 4DR SUV"])
        # The longest name wins: F-250 Super Duty is not the F-150.
        self.assertEqual(facts("Ford", "F-250", Source.CANADA).curb_weight_max, 6888)
        self.assertEqual(facts("Ford", "F150", Source.CANADA).curb_weight_max, 4942)
        self.assertEqual(report.counts["model years added"], 4)
        self.assertEqual(report.counts["models added"], 0)

    def test_rows_that_do_not_match_are_listed_not_guessed(self):
        report = self.run_import()["canada"]
        unmatched = "\n".join(report.unmatched)
        self.assertEqual(len(report.unmatched), 3)
        self.assertIn("2019 TOYOTA 86 2DR COUPE: no catalog model", unmatched)
        self.assertIn("2019 FORD ECOSPORT 4DR SUV: no catalog model", unmatched)
        self.assertIn("2019 FORD TRANSIT 250 VAN: begins with Transit but goes on with 250", unmatched)
        self.assertFalse(VehicleModelYear.objects.filter(source=Source.CANADA, vehicle_model__model="Transit").exists())
        self.assertEqual(report.rejected, ["2019 FORD MYSTERY TRIM: no weight or dimensions"])

    def test_motorcycle_makes_are_not_asked_for(self):
        # No Harley-Davidson file is in the cache, so asking would download.
        report = self.run_import()["canada"]
        self.assertEqual(report.counts["files from the cache"], 3)
        self.assertEqual(report.counts["files downloaded"], 0)

    def test_matching_rules(self):
        options = {1: ("SILVERADO", "Silverado"), 2: ("GRANDCHEROKEE", "Grand Cherokee"),
                   3: ("CHEROKEE", "Cherokee"), 4: ("CRV", "CR-V"), 5: ("3SERIES", "3 Series")}
        self.assertEqual(canada.match(options, canada.words("GRAND CHEROKEE 4DR SUV 4WD")), (2, None))
        self.assertEqual(canada.match(options, canada.words("CHEROKEE TRAILHAWK")), (3, None))
        self.assertEqual(canada.match(options, canada.words("SILVERADO 1500 CREW CAB"))[0], None)
        self.assertEqual(canada.match(options, canada.words("SILVERADO HD CREW CAB"))[0], None)
        self.assertEqual(canada.match(options, canada.words("SILVERADO CREW CAB 4WD")), (1, None))
        self.assertEqual(canada.match(options, canada.words("CR-V EX 4DR SUV")), (4, None))
        self.assertEqual(canada.match(options, canada.words("3-SERIES 330i xDRIVE 4DR SEDAN")), (5, None))
        self.assertEqual(canada.match({7: ("PROMASTER2500", "ProMaster 2500")},
                                      canada.words("PROMASTER 2500 159 IN. WB WINDOWED VAN")), (7, None))
        self.assertEqual(canada.match({8: ("RS", "RS")}, canada.words("RS 6 AVANT"))[0], None)
        # The name must end where a word ends: "CR-V" does not begin "CRVX".
        self.assertEqual(canada.match(options, canada.words("CRVX 4DR"))[0], None)
        model_id, why = canada.match({**options, 6: ("CRV", "CR V")}, canada.words("CR-V EX"))
        self.assertEqual((model_id, why), (None, "matches CR V and CR-V equally"))

    def test_a_make_the_canadian_data_spells_differently(self):
        ram = VehicleModel.objects.create(make="Ram", model="ProMaster 2500", source=VehicleModel.Source.NHTSA)
        VehicleModelYear.objects.create(vehicle_model=ram, year=2024, source=Source.VPIC)
        rows = [("Ram", 2024, {"Make": "RAM TRUCKS", "Model": "PROMASTER 2500 HIGH ROOF CARGO VAN", "CW": "5170"})]
        report = mock.Mock(unmatched=[], rejected=[])
        grouped = canada.facts_by_model_year(rows, report)
        self.assertEqual(grouped, {})
        report.reject.assert_called_once()
        grouped = canada.facts_by_model_year(rows, report, Names.from_data({"make_aliases": {"RAM TRUCKS": "Ram"}}))
        self.assertEqual(grouped[(ram.pk, 2024)].values()["curb_weight_max"], 5170)


class OwnerRecordsTests(CachedFixtures, TestCase):
    def test_imports_never_change_the_owners_records(self):
        rav4 = VehicleModel.objects.create(make="Toyota", model="RAV4", year_from=2016, year_to=2018,
                                           source=VehicleModel.Source.OWNER)
        own = VehicleModelYear.objects.create(vehicle_model=rav4, year=2019, source=Source.OWNER,
                                              curb_weight_min=3500, curb_weight_max=3600, body_styles=["four-door"])
        report = self.run_import()["epa"]
        rav4.refresh_from_db()
        self.assertEqual((rav4.make, rav4.model, rav4.year_from, rav4.year_to), ("Toyota", "RAV4", 2016, 2018))
        self.assertEqual(rav4.source, VehicleModel.Source.OWNER)
        self.assertEqual(rav4.history.count(), 1)
        own.refresh_from_db()
        self.assertEqual((own.curb_weight_min, own.curb_weight_max, own.body_styles), (3500, 3600, ["four-door"]))
        # The sources' own facts are recorded beside the owner's model.
        self.assertTrue(VehicleModelYear.objects.filter(vehicle_model=rav4, source=Source.EPA).exists())
        self.assertTrue(VehicleModelYear.objects.filter(vehicle_model=rav4, source=Source.CANADA).exists())
        self.assertEqual(report.counts["owner's models: facts recorded, model left alone"], 1)
        self.assertEqual(VehicleModel.objects.filter(make="Toyota", model="RAV4").count(), 1)

    def test_a_model_split_by_the_owner_gets_the_years_its_range_holds(self):
        older = VehicleModel.objects.create(make="Toyota", model="RAV4", year_from=2013, year_to=2018,
                                            source=VehicleModel.Source.OWNER)
        newer = VehicleModel.objects.create(make="Toyota", model="RAV4", year_from=2019, year_to=None,
                                            source=VehicleModel.Source.OWNER)
        self.run_import(["epa"])
        self.assertTrue(VehicleModelYear.objects.filter(vehicle_model=newer, year=2019).exists())
        self.assertFalse(VehicleModelYear.objects.filter(vehicle_model=older).exists())


class RunRecordTests(CachedFixtures, TestCase):
    def test_a_dry_run_changes_nothing_but_is_recorded(self):
        reports = self.run_import(dry_run=True)
        # The dry run matched the Canadian rows to models the same dry run added.
        self.assertEqual(reports["canada"].counts["model years added"], 4)
        self.assertFalse(VehicleModel.objects.exists())
        self.assertFalse(VehicleModelYear.objects.exists())
        runs = VehicleDataImportRun.objects.order_by("started_at")
        self.assertEqual([(r.source, r.dry_run, r.result) for r in runs],
                         [("epa", True, "succeeded"), ("vpic", True, "succeeded"), ("canada", True, "succeeded")])
        self.assertEqual(runs[0].counts["models added"], 4)
        self.assertEqual(runs[0].counts["rejected"], 1)
        self.assertLessEqual(runs[0].started_at, runs[0].finished_at)

    def test_a_failed_source_is_recorded_and_stops_the_run(self):
        (self.cache / "vpic" / "ford-2019-truck.json").unlink()
        reports = self.run_import()
        self.assertEqual(reports["epa"].result, "succeeded")
        self.assertEqual(reports["vpic"].result, "failed")
        self.assertIn("the test tried to download", reports["vpic"].message)
        self.assertNotIn("canada", reports)
        # The EPA's work is kept; the failed source wrote nothing.
        self.assertEqual(VehicleModel.objects.count(), 4)
        self.assertFalse(VehicleModelYear.objects.filter(source=Source.VPIC).exists())
        failed = VehicleDataImportRun.objects.get(source="vpic")
        self.assertEqual((failed.result, failed.dry_run), ("failed", False))


class CommandTests(CachedFixtures, TestCase):
    def call(self, *args):
        out = io.StringIO()
        with override_settings(VEHICLE_DATA_CACHE_DIR=self.cache), \
                mock.patch("vehicles.management.commands.import_vehicle_data.load_config", return_value=CONFIG), \
                mock.patch("urllib.request.urlopen", no_network):
            call_command("import_vehicle_data", *args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_the_report(self):
        output = self.call("--source", "all")
        self.assertIn("APPLIED", output)
        self.assertIn("EPA FuelEconomy.gov: succeeded", output)
        self.assertIn("models added: 4", output)
        self.assertIn("Models added (6)", output)
        self.assertIn("Canadian rows not matched to a model, left for the owner (3)", output)
        self.assertIn("2019 FORD MYSTERY TRIM: no weight or dimensions", output)

    def test_dry_run_of_one_source(self):
        output = self.call("--source", "epa", "--dry-run")
        self.assertIn("DRY RUN", output)
        self.assertNotIn("NHTSA vPIC:", output)
        self.assertFalse(VehicleModel.objects.exists())

    def test_a_failure_fails_the_command(self):
        (self.cache / "epa" / "vehicles.csv.zip").unlink()
        with self.assertRaisesMessage(CommandError, "EPA FuelEconomy.gov failed"):
            self.call("--source", "epa")

    def test_a_missing_cache_folder_is_refused(self):
        with override_settings(VEHICLE_DATA_CACHE_DIR=self.cache / "missing"):
            with self.assertRaisesMessage(CommandError, "VEHICLE_DATA_CACHE_DIR"):
                call_command("import_vehicle_data", stdout=io.StringIO())


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FetcherTests(SimpleTestCase):
    def setUp(self):
        self.cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.cache)
        self.waits = []

    def fetcher(self, answers, retry_after=None, **options):
        calls = []

        def opener(request, timeout=None):
            calls.append(request.full_url)
            answer = answers.pop(0)
            if isinstance(answer, int):
                headers = {"Retry-After": retry_after} if retry_after else {}
                raise urllib.error.HTTPError(request.full_url, answer, "error", headers, None)
            return FakeResponse(answer)

        fetcher = Fetcher(self.cache, pause_seconds=1, retries=3, backoff_seconds=5, opener=opener,
                          sleep=self.waits.append, **options)
        return fetcher, calls

    def test_429_and_5xx_are_retried_with_a_growing_wait(self):
        fetcher, calls = self.fetcher([429, 503, b"{}"])
        self.assertEqual(fetcher.get("https://x.invalid/a", "a.json"), b"{}")
        self.assertEqual(self.waits, [5, 10])
        self.assertEqual(len(calls), 3)

    def test_retry_after_is_honored(self):
        fetcher, _ = self.fetcher([429, b"{}"], retry_after="30")
        fetcher.get("https://x.invalid/a", "a.json")
        self.assertEqual(self.waits, [30])

    def test_gives_up_after_the_retries_and_on_other_errors(self):
        fetcher, calls = self.fetcher([500, 500, 500, 500])
        with self.assertRaisesMessage(FetchError, "HTTP 500"):
            fetcher.get("https://x.invalid/a", "a.json")
        self.assertEqual(len(calls), 4)
        fetcher, calls = self.fetcher([404])
        with self.assertRaisesMessage(FetchError, "HTTP 404"):
            fetcher.get("https://x.invalid/b", "b.json")
        self.assertEqual(len(calls), 1)

    def test_cached_files_are_not_fetched_again_and_calls_are_paced(self):
        fetcher, calls = self.fetcher([b"one", b"two"])
        fetcher.get("https://x.invalid/a", "vpic/a.json", pace="vpic")
        fetcher.get("https://x.invalid/b", "vpic/b.json", pace="vpic")
        fetcher.get("https://x.invalid/a", "vpic/a.json", pace="vpic")
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.waits, [1])
        self.assertEqual((fetcher.downloaded, fetcher.from_cache), (2, 1))
        self.assertEqual((self.cache / "vpic" / "b.json").read_bytes(), b"two")

    def test_refresh_fetches_each_file_again_once(self):
        (self.cache / "a.json").write_bytes(b"old")
        fetcher, calls = self.fetcher([b"new"], refresh=True)
        self.assertEqual(fetcher.get("https://x.invalid/a", "a.json"), b"new")
        self.assertEqual(fetcher.get("https://x.invalid/a", "a.json"), b"new")
        self.assertEqual(len(calls), 1)

    def test_a_body_that_fails_its_check_is_not_cached(self):
        fetcher, _ = self.fetcher([b"<html>busy</html>"])

        def check(body):
            raise ValueError("not JSON")

        with self.assertRaisesMessage(FetchError, "not JSON"):
            fetcher.get("https://x.invalid/a", "a.json", check=check)
        self.assertEqual(list(self.cache.iterdir()), [])


class ConfigTests(SimpleTestCase):
    def test_reads_the_real_data_files(self):
        config = load_config(today=datetime.date(2026, 10, 22))
        self.assertEqual(config.epa_url, "https://www.fueleconomy.gov/feg/epadata/vehicles.csv.zip")
        self.assertTrue(config.vpic_url.startswith("https://vpic.nhtsa.dot.gov/api/"))
        self.assertEqual((config.year_from, config.year_to), (1984, 2027))
        self.assertIn("Harley-Davidson", [make.name for make in config.motorcycle_makes])
        self.assertEqual(len(config.motorcycle_makes), 16)
        self.assertIn("RAM", next(make for make in config.truck_makes if make.name == "Ram").vpic_names)
        self.assertEqual(config.names.make_key("RAM TRUCKS"), "RAM")
        self.assertGreater(config.pause_seconds, 0)

    def test_the_cache_is_outside_the_repository(self):
        # The repository's two folders, app/ and data/, wherever they are mounted.
        cache = Path(settings.VEHICLE_DATA_CACHE_DIR).resolve()
        for folder in (settings.DATA_DIR.resolve(), Path(__file__).resolve().parents[1]):
            self.assertNotEqual(cache, folder)
            self.assertNotIn(folder, cache.parents)
