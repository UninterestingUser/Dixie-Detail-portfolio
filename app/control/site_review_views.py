"""The Reviews screen (decision 0109): the customer reviews the website
shows, kept only in the database so customers' names never enter the
repository. Managers only. Every saved change asks Cloudflare Pages to
rebuild the site, which reads the shown reviews from the public API, as a
pricebook publish does (pricebook.site_rebuild)."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from marketing.models import Review
from pricebook.site_rebuild import request_rebuild

from .forms import ReviewForm
from .location_views import require_manager

REBUILDING = "The website shows the change after its rebuild, in a few minutes."


def changed(request, what):
    """Record what changed and ask for a rebuild once it is saved."""
    messages.success(request, f"{what} {REBUILDING}")
    transaction.on_commit(lambda: request_rebuild("reviews changed"))


def renumber(reviews):
    for position, review in enumerate(reviews):
        if review.position != position:
            review.position = position
            review._change_reason = "Reordered in the control app"
            review.save(update_fields=["position"])


@require_safe
def reviews(request):
    require_manager(request, "see or change the website's reviews")
    return render(request, "control/reviews.html", {"reviews": list(Review.objects.all())})


def review_form(request, pk=None):
    require_manager(request, "see or change the website's reviews")
    review = get_object_or_404(Review, pk=pk) if pk else None
    form = ReviewForm(request.POST or None, instance=review)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save(commit=False)
            if review is None:
                last = Review.objects.order_by("-position").first()
                saved.position = last.position + 1 if last else 0
            saved._change_reason = "Saved in the control app"
            saved.save()
            changed(request, f"Saved the review by {saved.name}.")
        return redirect("site-reviews")
    return render(request, "control/review_form.html", {"form": form, "review": review})


@require_POST
@transaction.atomic
def review_move(request, pk):
    require_manager(request, "change the website's reviews")
    rows = list(Review.objects.select_for_update().order_by("position", "pk"))
    index = next((i for i, row in enumerate(rows) if row.pk == pk), None)
    if index is None:
        return redirect("site-reviews")
    other = index - 1 if request.POST.get("direction") == "up" else index + 1
    if 0 <= other < len(rows):
        rows[index], rows[other] = rows[other], rows[index]
        renumber(rows)
        changed(request, f"Moved the review by {rows[other].name} {'up' if other < index else 'down'}.")
    return redirect("site-reviews")


@require_POST
@transaction.atomic
def review_shown(request, pk):
    require_manager(request, "change the website's reviews")
    review = get_object_or_404(Review.objects.select_for_update(), pk=pk)
    review.shown = request.POST.get("shown") == "on"
    review._change_reason = "Shown or hidden in the control app"
    review.save(update_fields=["shown"])
    changed(request, f"{'Showing' if review.shown else 'Hid'} the review by {review.name}.")
    return redirect("site-reviews")


def review_delete(request, pk):
    require_manager(request, "delete a review")
    review = get_object_or_404(Review, pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            name = review.name
            review._change_reason = "Deleted in the control app"
            review.delete()
            renumber(list(Review.objects.order_by("position", "pk")))
            changed(request, f"Deleted the review by {name}.")
        return redirect("site-reviews")
    return render(request, "control/review_delete.html", {"review": review})
