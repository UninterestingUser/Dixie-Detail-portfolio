---
title: Managing the website's reviews
summary: How a manager adds, edits, reorders, shows or hides and deletes the customer reviews the website shows, on the control app's Reviews screen, and when a change appears on the site.
audience: [owner]
visibility: internal
status: current
updated: 2026-11-19
tags: [guides, reviews, website, control-app]
related: [docs/decisions/0109-reviews-kept-in-the-control-app.md, docs/reference/website-and-seo.md, docs/reference/control-app.md, docs/reference/public-api.md]
---

# Managing the website's reviews

The reviews on the website's homepage and reviews page are kept in the control app, never in the repository, so customers' names stay private to the business ([decision 0109](../decisions/0109-reviews-kept-in-the-control-app.md)). Only a manager can see or change them.

## Open the Reviews screen

**Account → Reviews.** The list is in the website's order: the first three shown reviews are on the homepage, and every shown review is on `/reviews/`. A hidden review is marked **Hidden** and faded.

## Add a review

1. Copy the review from Google.
2. Tap **Add a review**.
3. Fill in:
   - **Reviewer's name:** first name and last initial, as on Google, such as "Pat Q.".
   - **Review:** the text, as written.
   - **Date of the review.**
   - **Star rating** (optional): 1 to 5, or **No rating**.
   - **Link to the Google review** (optional): the review's share link, starting with https://.
   - **Shown on the website:** ticked to show it.
4. Tap **Save**. A new review goes to the end of the list; move it up to show it sooner.

## Change the order, hide or delete

- **Move up** and **Move down** change its place.
- **Hide** takes a review off the website and keeps it here; **Show** puts it back.
- **Edit** changes it. To delete one for good, open it with **Edit**, tap **Delete this review**, then **Delete for good**.

## When the website shows a change

Every saved change asks Cloudflare Pages to rebuild the site, so it shows within a few minutes. If a change hasn't appeared after ten minutes, the rebuild may have failed: the control app's log says so, and `python manage.py rebuild_website` asks again ([website-and-seo.md](../reference/website-and-seo.md#how-content-stays-current)).

The site never shows a combined rating. With no review shown, the reviews section links to the Google reviews only.
