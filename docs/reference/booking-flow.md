---
title: Customer booking flow
summary: The seven booking steps on the website, the running estimate card, address and phone entry, the quote request form, and the request a time form used while the server or Google can't be reached.
audience: [owner, staff, developer]
visibility: internal
status: current
updated: 2026-11-18
tags: [booking, website, estimate-card, phase-3]
related: [docs/decisions/0105-the-website-on-cloudflare-pages.md, docs/guides/previewing-and-deploying-the-website.md, docs/decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md, docs/reference/public-api.md, docs/decisions/0099-quote-requests-with-photos.md, docs/decisions/0100-public-api-quotes-and-bookings.md, docs/decisions/0065-condition-lengthens-service-time.md, docs/decisions/0072-motorcycles-class.md, docs/reference/vehicle-classification.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/reference/pricing.md, docs/reference/scheduling-and-calendars.md, docs/reference/returning-customers.md, docs/reference/text-messages.md, docs/reference/website-and-seo.md]
---

# Customer booking flow

This is how the website's booking page at `/book/` works, built in Phase 3, Step 6 to the mockups approved on the design canvas "Dixie Detail Website Mockups" ([decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md)). It runs on the staging site until the Phase 5 launch; until then customers book through Setmore. Each endpoint it calls is described in [public-api.md](public-api.md). The code is in `site/src/pages/book.astro` and `site/src/scripts/booking/`.

The flow follows the Armstrong "Build Your Detail" screens the owner chose as a model, with a running estimate card, and goes one step further: it ends in a confirmed appointment instead of an estimate. Armstrong's wax-upgrade step is left out because ceramic wax is included in every detail.

## The seven steps

1. **Vehicle.** Year, then make, then model. The homepage's "Get your exact price" picker opens this page with them filled in. A banner confirms the vehicle class, such as "Medium identified", with that class's starting price. A cab or third-row question appears only when the vehicle data cannot settle the size variant. Motorcycle models appear in the same year, make and model lists as cars, each with a small "Motorcycle" label, so a Honda Gold Wing and a Honda Accord are easy to tell apart; a motorcycle is in the Motorcycles class, with no size question ([decision 0072](../decisions/0072-motorcycles-class.md)). A vehicle not in the lists, such as a pre-1984 classic, is chosen from eight photo cards, one per vehicle class, Motorcycles among them; the Full-size Vans card, "Ask for a quote", leads to a quote request instead (below), because that class is not booked online (decisions [0083](../decisions/0083-applying-the-size-based-classes.md) and [0099](../decisions/0099-quote-requests-with-photos.md)). The class, size and question come from one lookup on the server ([vehicle-classification.md](vehicle-classification.md#the-lookup)). A "My vehicle isn't listed" link opens the photo cards too, where the customer can type the year, make and model they know and pick the size when the class has more than one. An optional Color box comes last; it is used only to tell a returning customer's identical vehicles apart and never changes the price ([decision 0067](../decisions/0067-color-tells-identical-vehicles-apart.md)).
2. **Service and add-ons.** Service cards show the prices for the vehicle's class and size, before any condition adjustment, each with the owner's short text from [data/site-content.yaml](../../data/site-content.yaml). Picking one asks the server for a quote, and the estimate card fills in. Add-ons are tick boxes with their added price. Maintenance plans never appear here. A motorcycle is offered only Motorcycle Detail, with no add-ons.
3. **Condition (service level).** Only when the chosen service covers the interior: Full Detail or Interior Only ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md)). Every other service, Exterior Only and Motorcycle Detail included, skips this step and has no condition level. Three cards with plain descriptions, Service Level 1 picked to start: Level 1 adds nothing and Level 2 adds 10%. Level 3 shows no price or time: it is "Ask for a quote", and choosing it turns the form into a quote request carrying the service, the level and the add-ons already ticked (below).
4. **Location.** The service address, validated as the customer types (see below). It is checked against the service area and sets the sales tax rate, with a reminder that water and power are needed. An address outside the area is refused with the business's number to call or text.
5. **Date and time.** A month calendar of the days the availability check offers, with closed, booked and too-soon days crossed out, then the arrival times for the day picked. The start times come from that weekday's start-times setting (8:00, 8:30 and 9:00 AM on every open day at launch), and a start time is shown only when the whole time on site fits. See [scheduling-and-calendars.md](scheduling-and-calendars.md).
6. **Details.** First name, an optional last name, mobile number, preferred payment method, and two unchecked consent checkboxes: appointment texts and follow-up texts, in the exact wording the server serves ([data/consent-wording.yaml](../../data/consent-wording.yaml)), with the Privacy Policy and Text Message Terms linked. Nothing is charged.
7. **Review and confirm.** The full estimate. A Cloudflare Turnstile check runs when the customer presses Book, out of sight unless Cloudflare asks them to tick it. Then the confirmation, with the booking reference, an "Add to my calendar" file, and a confirmation text (with consent). The booking refers to the server's quote, never to a price sent from the browser. A quote lasts 2 hours (a setting); booking an expired one, or one the chosen day would price differently, shows a fresh quote to confirm instead of booking at a new price. A time someone else took a moment earlier is refused, and the form offers the open times again.

## How the steps behave

- The step indicator at the top is display only. It shows finished steps, the current step and grayed-out future steps; customers cannot jump ahead by clicking it.
- Only steps already reached are shown. Finishing a step reveals the next card below and scrolls to it. Earlier cards stay visible and can still be changed.
- "Start over" is a separate outlined button below the estimate card, not a text link.
- Changing an earlier step makes it the current step again: the steps after it hide until it is finished, keeping what they held. A new choice that changes the price asks the server for a new quote, and a new quote clears the time picked, because its time on site may differ.
- The Continue button says what is still missing, such as "Pick a service to continue", until the step is complete.

## The estimate card

- **Always in view.** It sits beside the steps on a desktop, and becomes a navy bar pinned to the bottom of a phone screen that opens into a full sheet when tapped.
- **Builds line by line.** Vehicle and class, the service, each add-on, the condition adjustment once the condition step is reached, sales tax once the address is known, the total and the estimated time on site (setup, service time and breakdown together). Level 2 lengthens the time as well as the price, so changing the level changes both ([decision 0065](../decisions/0065-condition-lengthens-service-time.md)). Level 3 has no price or time, so with it picked the card shows "Ask for a quote" in place of the total and time ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md)). Before the address, the card says the total is before sales tax.
- **Shows the server's numbers only.** Every price, total and time on the card comes from the server's quote, shown as it arrives; the website does no arithmetic of its own ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)). A check in CI refuses any arithmetic beside a money name in the booking code, and the browser tests use a fake server whose totals are deliberately not the sums of their lines.
- **Shows "full day"** instead of hours when the one-person time on site is 8 hours or more, condition time included.
- **Sets expectations.** It states that the final price is confirmed when the vehicle is seen, and that nothing is charged until the job is done.

## Address entry is validated as the customer types

The address field works like a Shopify checkout: suggestions appear as the customer types, and the address must be a real one. The system uses Google Places Autocomplete (New), restricted to US addresses and biased to the service area, with a session token. Picking a suggestion sends the server only the place ID and the session token. The server looks the place up itself with its own key, asking only for the address parts, formatted address and location; that call ends the session, so the suggestions before it are not billed. The server then runs the service-area check and the tax lookup ([sales-tax.md](sales-tax.md)). Coordinates from the browser are never used. There is no separate "check" button. Addresses outside the service area are refused unless the owner has approved them. The Google Address Validation API may be added later to catch missing unit numbers. The field calls Google's Places Autocomplete (New) web service from the browser with the browser key (`PUBLIC_GOOGLE_MAPS_BROWSER_KEY`), so the session token is the website's own and the server's lookup can end the same session. Suggestions can be picked with the arrow keys and Enter. When Google refuses or fails, such as once the day's limit is used up, the form switches to the request a time form below, with the address typed.

## Phone number entry

The mobile number field formats itself as (###) ###-#### while the customer types and requires 10 digits. The number is stored as 10 digits and used for quiet matching; see [returning-customers.md](returning-customers.md).

## The Color box

The vehicle step's Color box is optional free text, such as "silver" or "dark blue", and the step can be finished without it. It is used only when quiet matching finds a returning customer with more than one vehicle of the same make, model and year: the color picks the right one. A blank color, or one that matches none of them, never stops the booking; the appointment books and the control app asks the owner which vehicle it was. The color is not a price input, so it never appears on the estimate card or changes the quote. The full rule is in [returning-customers.md](returning-customers.md).

## Quote requests for jobs the site can't price

Two kinds of job can't be booked online:

- **A vehicle in a class booked by quote,** today only Full-size Vans ([decision 0099](../decisions/0099-quote-requests-with-photos.md)). After the vehicle step the form says so and becomes a quote request.
- **Full Detail or Interior Only at Service Level 3** ([decision 0103](../decisions/0103-service-levels-for-interior-work-and-level-3-by-quote.md)). Picking Level 3 in the condition step turns the form into a quote request, keeping the vehicle, the service and the add-ons already chosen.

The quote request takes:

- the service wanted, or "Not sure" (a Level 3 request keeps its service), with the condition level and any add-ons;
- a required description of what's needed;
- the service address, checked as in step 4;
- the name, mobile number and the two consent checkboxes;
- an optional note on preferred days;
- up to 6 photos, optional, under "Photos are optional, but they help us give you an accurate quote." Each uploads as it is picked, so a slow one never loses the form, and shows a thumbnail, a remove button and its upload progress. The browser shrinks a photo to at most 2560 pixels before sending it when it can read it; iPhone HEIC photos it can't read go as they are, and are accepted.
- a Turnstile check when the request is sent, and one when the first photo is picked, to open the upload session.

The "What do you need?" box asks for the details that matter for the price, such as length, size, conversions and condition. Sending it books nothing and holds no time: the customer is told Dixie Detail will reply with a price. The owner sees the request with its photos in the control app, with the Level 2 price beside a Level 3 request for reference. A class or level the owner later sets to "Ask for a quote", such as RVs or boats, uses the same form.

## Other cases

- **A second vehicle the same day** is taken as a request the owner approves. When quiet matching finds the customer already has a job that day, the booking becomes a request instead of an appointment, and the form tells the customer Dixie Detail will confirm it by text or call ([public-api.md](public-api.md#booking-post-bookings), [returning-customers.md](returning-customers.md#a-second-vehicle-the-same-day)). The time must still be open, so at launch this is a second motorcycle; a day takes one job otherwise.


## When the server can't be reached

The site is static on Cloudflare, so its pages and built-in prices load even when the home server is down. When the booking page can't reach the server (no answer, a timeout or a server error), or Google's address suggestions fail, a notice says so and the form becomes a **request a time** form ([decision 0105](../decisions/0105-the-website-on-cloudflare-pages.md)):

- **The vehicle** is picked from the photo cards, with the year, make and model typed if known, and the size when the class has more than one. A vehicle the server already settled stays settled.
- **The service, add-ons and condition** work as above. The estimate card shows the server's own total for the job from the price table baked into the page when it was built (`GET price-table`), marked as before sales tax and from that pricebook version. The browser looks the total up and never works it out.
- **The address** uses Google's suggestions while they work; otherwise it is typed, and the owner checks it.
- **The date and time** are a preferred day, a preferred arrival from that weekday's start times or "any time", and an optional note. Nothing is booked.
- **Details and consents** are as in step 6, with Turnstile when the customer presses Send.

Cloudflare's offline piece takes the form. It checks the Turnstile token, tries the server at once, signed, and otherwise holds the request until the server answers, replaying it every 5 minutes ([public-api.md](public-api.md#offline-requests-post-time-requests), [decision 0100](../decisions/0100-public-api-quotes-and-bookings.md)). The server prices it on arrival, keeps it as a request rather than an appointment, and flags it for the owner if the price differs from what the customer saw. The customer is told Dixie Detail will confirm the day and price by text or call.

A quote request sent while the server can't be reached goes the same way, without photos: the form says photos can be sent later and gives the number to text them to.

Any network failure, timeout or server error (5xx) from the API counts as the server being unreachable, whenever it happens. That includes Cloudflare's own error pages, such as the 530 while the tunnel is down: they carry no CORS headers, so the browser sees them as a network failure. A call the server answers with a refusal (4xx) is not an outage; the form shows the server's message.

## When a send fails

No send waits forever. A booking, a quote request and a request a time each give up after a set time: 45 seconds for the Turnstile check (long enough to tick the box if Cloudflare asks), then 15 seconds for the server, or 20 for Cloudflare's offline piece, which tries the server first. Each photo upload gives up after 3 minutes. A Turnstile check that can't start, reports an error or returns no token counts as a failure, and nothing is sent. When a send fails, the button comes back, a plain message says nothing was sent and gives the business phone number, and everything the customer entered stays in the form, so trying again is one press. A booking that fails because the server can't be reached becomes the request a time form instead, keeping the vehicle, service and details.
