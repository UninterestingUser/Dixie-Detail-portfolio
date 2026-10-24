"""What the monthly vehicle data refresh may change on its own (decision 0081).

A refresh adds new models and model years, which go live when the rules
classify them cleanly, and updates facts. It never changes the vehicle class
or size of a model year that is already live when its model has a model
override, an approval on the approval list, or customers' jobs: hold() sends
that model year to the review queue instead, keeping its class meanwhile,
with the old and the new class in the reason and the new one as the
suggestion. A model year a refresh held stays held until the owner settles
it, even if the approval that protected it has since been cleared.

classify_vehicles --refresh applies this; the owner's own changes in the
control app and classify_vehicles by hand do not, because the owner sees
their preview first.
"""

from collections import defaultdict

from vehicles.models import ModelApproval, ModelOverride, ModelYearClassification

from .engine import Kind, Method, Result, _live, class_label, size_label

HAS_OVERRIDE = "it has a model override"
HAS_APPROVAL = "it has an approval on the approval list"
IN_JOB_HISTORY = "it is in the job history"
HELD_BEFORE = "an earlier refresh held it"


def _ids(vehicle_class, size_variant, ask):
    return getattr(vehicle_class, "pk", None), getattr(size_variant, "pk", None), ask


def protected_models():
    """{model id: [why]} for every model whose live classes a refresh may
    not change."""
    from vehicles.linking import job_history_models

    found = defaultdict(list)
    for model_id in sorted(set(ModelOverride.objects.values_list("vehicle_model_id", flat=True))):
        found[model_id].append(HAS_OVERRIDE)
    for model_id in sorted(set(ModelApproval.objects.filter(cleared_at=None).values_list("vehicle_model_id", flat=True))):
        found[model_id].append(HAS_APPROVAL)
    for model_id in sorted(job_history_models()):
        found[model_id].append(IN_JOB_HISTORY)
    return dict(found)


def hold(results, stored=None, protected=None):
    """Hold, in results ({(model id, year): (ModelYear, Result)} from
    classify_catalog), every change a refresh may not make on its own.
    Returns [(ModelYear, old label, new label)] for the model years held."""
    if stored is None:
        stored = {
            (row.vehicle_model_id, row.year): row
            for row in ModelYearClassification.objects.select_related("vehicle_class", "size_variant")
        }
    protected = protected_models() if protected is None else protected
    held = []
    for key, (model_year, result) in results.items():
        before = stored.get(key)
        if result.in_review or before is None or before.vehicle_class_id is None:
            # Already waiting for the owner, or new: nothing live to protect.
            continue
        old_class, old_size, old_ask = _live(before)
        if _ids(old_class, old_size, old_ask) == _ids(result.vehicle_class, result.size_variant, result.ask_size):
            continue
        why = list(protected.get(key[0], []))
        if before.in_review and Kind.HELD in before.review_kinds:
            why.append(HELD_BEFORE)
        if not why:
            continue
        old_label = class_label(old_class, size_label(old_size, old_ask, old_class))
        new_label = class_label(result.vehicle_class, size_label(result.size_variant, result.ask_size, result.vehicle_class))
        reason = (
            f"the monthly refresh would change this from {old_label} to {new_label}"
            f" ({result.because}); held because {' and '.join(why)}"
        )
        results[key] = (
            model_year,
            Result(
                method=Method.REVIEW,
                reasons=[reason],
                kinds=[Kind.HELD],
                suggested_class=result.vehicle_class,
                suggested_size=result.size_variant,
                suggested_ask=result.ask_size,
            ),
        )
        held.append((model_year, old_label, new_label))
    return held
