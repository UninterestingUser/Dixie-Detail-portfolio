"""The vehicle data import (docs/operations/importing-vehicle-data.md).

Loads the vehicle catalog from three free sources: the EPA's FuelEconomy.gov
table, NHTSA vPIC's model lists, and vPIC's Canadian specifications. Each
source writes only its own facts per model year (VehicleModelYear), so no
source overwrites another, and nothing with source "owner" is ever changed.
"""
