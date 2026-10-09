# Scheduling

The core app owns scheduling. Google Calendar is a mirror and a source of days off, never the source of truth.

## Booking rules

- **Working days:** closed Sundays. Holidays and days off are set in the control app or on the Time Off calendar.
- **Notice:** no same-day or next-day booking. The earliest bookable day is two days out.
- **Arrival times:** 8:00, 8:30 or 9:00 AM, the same for every service.
- **Capacity:** one job per day, except that two Monthly Maintenance jobs can share a day. Every other service takes the whole day, whatever its length.
- **Second Monthly Maintenance job:** starts at the first job's scheduled end plus the drive time between the two addresses, with a 30-minute minimum, rounded up to the next quarter hour. Example: an 8:00 job of 3 hours followed by a 42-minute drive puts the second at 11:45.
- **Maintenance:** Monthly and Quarterly Maintenance never appear on the website. The owner books them in the control app, as a single visit or a repeating series.
- **Second vehicle, same day:** the public form takes it as a request the owner approves.

## Customer booking flow

1. Vehicle: year, make, model. The class is identified automatically; a doors, cab or third-row question appears only when needed.
2. Condition: three cards.
3. Service and add-ons, priced for the vehicle.
4. Location: address with suggestions, service-area check, sales tax rate.
5. Date and arrival time.
6. Details: name, mobile number, preferred payment method, and two unchecked consent checkboxes (appointment texts; follow-up texts).
7. Review and confirm.

A running estimate card stays in view throughout: beside the steps on a desktop, a bar pinned to the bottom of a phone screen.

## Google Workspace calendars

| Calendar | Who writes to it | What it holds |
| --- | --- | --- |
| Dixie Detail Jobs | The core app only | One event per appointment, the job address as the location, and a "Drive to job" block before it |
| Dixie Detail Time Off | The owner | Days off and holidays; an all-day event closes the day |

- The core app connects through a Google service account that the two calendars are shared with: edit on Jobs, read on Time Off.
- Customers are never added as event guests.
- Edits made to a Jobs event in Google are overwritten at the next sync. Appointments change in the control app.
- Both calendars use Eastern time.

## Time-to-leave alert

- Sent at drive time plus 10 minutes before the scheduled start. A 32-minute drive alerts 42 minutes ahead.
- Drive time runs from the home base, or from the previous job's address for a second job that day, using predicted traffic.
- Calculated at booking and refreshed the morning of the job.
- Delivered as a normal push notification from the control app to every staff member on the job, with a navigation link and an "On my way" button that texts the customer.
- The 10-minute buffer, the home base and each staff member's starting point are settings.
