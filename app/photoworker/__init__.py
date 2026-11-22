"""The photo worker (decision 0123): quote request photos are decoded here,
in a container with no network, no secrets and no database, one at a time,
each in a fresh process with a time limit. Nothing in this package imports
Django."""
