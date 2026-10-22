"""Vehicle classification (docs/reference/vehicle-classification.md,
decisions 0060 and 0073): the ordered rules and the overrides applied to each
model year's facts, the preview of a change, the review queue, and the
lookup the booking form uses.

- rules: the facts a rule can use and how a condition is tested.
- engine: classifying the whole catalog, the preview and applying it.
- seed: the launch rules, overrides and third-row list from data/.
- lookup: classify(year, make, model, answers=None).
"""
