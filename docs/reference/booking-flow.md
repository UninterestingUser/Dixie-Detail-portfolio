---
title: Customer booking flow
summary: The seven steps a customer follows on the website to book a job, how the running estimate card behaves, and how address and phone entry are validated.
audience: [owner, staff, developer]
visibility: internal
status: planned
updated: 2026-10-29
tags: [booking, website, estimate-card, phase-3]
related: [docs/decisions/0065-condition-lengthens-service-time.md, docs/decisions/0072-motorcycles-class.md, docs/reference/vehicle-classification.md, docs/decisions/0067-color-tells-identical-vehicles-apart.md, docs/decisions/0056-scheduling-rules-are-settings.md, docs/decisions/0059-quoted-price-is-price-of-record.md, docs/reference/pricing.md, docs/reference/scheduling-and-calendars.md, docs/reference/returning-customers.md, docs/reference/text-messages.md, docs/reference/website-and-seo.md]
---

# Customer booking flow

This is the Phase 3 design, approved in mockups on the design canvas "Dixie Detail Website Mockups". Until launch, customers book through Setmore.

The flow follows the Armstrong "Build Your Detail" screens the owner chose as a model, with a running estimate card, and goes one step further: it ends in a confirmed appointment instead of an estimate. Armstrong's wax-upgrade step is left out because ceramic wax is included in every detail.

## The seven steps

1. **Vehicle.** Year, then make, then model. A banner confirms the vehicle class, such as "Medium identified", with that class's starting price. A cab or third-row question appears only when the vehicle data cannot settle the size variant. Motorcycle models appear in the same year, make and model lists as cars, each with a small "Motorcycle" label, so a Honda Gold Wing and a Honda Accord are easy to tell apart; a motorcycle is in the Motorcycles class, with no size question ([decision 0072](../decisions/0072-motorcycles-class.md)). A vehicle not in the lists, such as a pre-1984 classic, is chosen from eight photo cards, one per vehicle class, Motorcycles among them; the Full-size Vans card asks the customer to send a photo for a quote, because that class is not booked online ([decision 0083](../decisions/0083-applying-the-size-based-classes.md)). The class, size and question come from one lookup on the server ([vehicle-classification.md](vehicle-classification.md#the-lookup)). An optional Color box comes last; it is used only to tell a returning customer's identical vehicles apart and never changes the price ([decision 0067](../decisions/0067-color-tells-identical-vehicles-apart.md)).
2. **Condition.** Three cards with plain descriptions. The first adds nothing, the second 10% and the third 20%. A motorcycle skips this step: Motorcycle Detail is a flat price.
3. **Service and add-ons.** Service cards show prices already adjusted for class, size and condition. Add-ons are tick boxes with their added price. Maintenance plans never appear here. A motorcycle is offered only Motorcycle Detail, with no add-ons.
4. **Location.** The service address, validated as the customer types (see below). It is checked against the service area and sets the sales tax rate, with a reminder that water and power are needed.
5. **Date and time.** Only the days and start times the availability check offers. The start times come from that weekday's start-times setting (8:00, 8:30 and 9:00 AM on every open day at launch), and a start time is shown only when the whole time on site fits. See [scheduling-and-calendars.md](scheduling-and-calendars.md).
6. **Details.** Name, mobile number, preferred payment method, and two unchecked consent checkboxes: appointment texts and follow-up texts. Nothing is charged.
7. **Review and confirm.** The full estimate, then a confirmation text (with consent) and a calendar file. The booking refers to the server's quote, never to a price sent from the browser.

## How the steps behave

- The step indicator at the top is display only. It shows finished steps, the current step and grayed-out future steps; customers cannot jump ahead by clicking it.
- Only steps already reached are shown. Finishing a step reveals the next card below and scrolls to it. Earlier cards stay visible and can still be changed.
- "Start over" is a separate outlined button below the estimate card, not a text link.

## The estimate card

- **Always in view.** It sits beside the steps on a desktop, and becomes a navy bar pinned to the bottom of a phone screen that opens into a full sheet when tapped.
- **Builds line by line.** Vehicle and class, the service, the condition adjustment, each add-on, sales tax once the address is known, the total and the estimated time on site (setup, service time and breakdown together). The condition level lengthens the time as well as the price, so changing it changes both ([decision 0065](../decisions/0065-condition-lengthens-service-time.md)). Before the address, the card says the total is before sales tax.
- **Shows the server's numbers only.** Every price, total and time on the card comes from the server's quote; the website does no arithmetic of its own ([decision 0059](../decisions/0059-quoted-price-is-price-of-record.md)).
- **Shows "full day"** instead of hours when the one-person time on site is 8 hours or more, condition time included.
- **Sets expectations.** It states that the final price is confirmed when the vehicle is seen, and that nothing is charged until the job is done.

## Address entry is validated as the customer types

The address field works like a Shopify checkout: suggestions appear as the customer types, and the address must be a real one. The system uses Google Places Autocomplete (New), restricted to US addresses and biased to the service area. Picking a suggestion returns verified address parts and coordinates, which drive the service-area check and the tax lookup. There is no separate "check" button. Addresses outside the service area are refused unless the owner has approved them. The Google Address Validation API may be added later to catch missing unit numbers.

## Phone number entry

The mobile number field formats itself as (###) ###-#### while the customer types and requires 10 digits. The number is stored as 10 digits and used for quiet matching; see [returning-customers.md](returning-customers.md).

## The Color box

The vehicle step's Color box is optional free text, such as "silver" or "dark blue", and the step can be finished without it. It will be used only when quiet matching finds a returning customer with more than one vehicle of the same make, model and year: the color picks the right one. A blank color, or one that matches none of them, never stops the booking; the appointment books and the control app asks the owner which vehicle it was. The color is not a price input, so it never appears on the estimate card or changes the quote. The full rule is in [returning-customers.md](returning-customers.md).

## Other cases

- **A second vehicle the same day** is taken as a request the owner approves.
- **If the server is offline,** the site and prices still load, and the form becomes a "request a time" form that Cloudflare holds until the server returns. The form shows prices from the last published pricebook. When the server returns, it prices each request, and the owner is notified if a price differs from what the customer saw.
