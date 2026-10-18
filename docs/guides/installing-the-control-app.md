---
title: Installing the control app on a phone or computer
summary: How to get a control app account, connect to Tailscale, sign in, and install the control app to the Pixel's home screen or a Fedora workstation, with what to do when it will not open or sign in.
audience: [owner, staff]
visibility: internal
status: current
updated: 2026-10-18
tags: [guides, control-app, install, tailscale, sign-in]
related: [docs/reference/control-app.md, docs/guides/finding-a-customer.md, docs/architecture/network-and-access.md, docs/decisions/0046-control-app-django-htmx.md, docs/decisions/0052-django-sign-in-over-tailscale.md, docs/decisions/0068-control-app-https-static-and-sign-in.md]
---

# Installing the control app on a phone or computer

The control app is a private web page on the home server that can be installed like an app. It opens only on devices connected to the business's Tailscale network, and everyone signs in with their own account. Its address is `https://` followed by the server's tailnet name, the first name in `DJANGO_ALLOWED_HOSTS`; [control-app.md](../reference/control-app.md) gives it in full.

## Step 1: Get an account

The owner creates each account on the server. The first account, the owner's, is a superuser, which can also open the Django admin:

```bash
cd /srv/dixie-detail
sudo docker compose exec app python manage.py createsuperuser
```

It asks for a username, an email address (can be left blank) and a password of at least 12 characters. For anyone else, create an ordinary account in the Django admin under **Users**, without the superuser box ticked. To reset a password: `sudo docker compose exec app python manage.py changepassword USERNAME`.

## Step 2: Connect the device to Tailscale

1. Install the Tailscale app and sign in to the business's tailnet. The owner approves new devices in the Tailscale admin console.
2. On a phone, open the Tailscale app's settings and turn on **Use Tailscale DNS**, so the phone can find the server by its tailnet name.
3. Leave Tailscale connected whenever you use the control app.

## Step 3: Sign in

Open the control app's address in Chrome and sign in with your username and password. You stay signed in on that device for two weeks, or until you tap **Account**, then **Sign out**.

## Step 4: Install it

**On the Pixel:**

1. In Chrome, with the control app open, tap the three-dot menu.
2. Tap **Add to home screen**, then **Install**.
3. The Dixie Detail icon, white "DD" on red, appears on the home screen. It opens in its own window, without Chrome's address bar.

**On a Fedora workstation:** in Chrome or Chromium, click the install icon at the right end of the address bar, or open the three-dot menu and choose **Cast, save and share**, then **Install page as app**. It then appears in the app list like any other program. Firefox cannot install web apps; bookmark the address instead.

## Using it with one hand

The bar along the bottom of the phone screen has the three places you need: **Customers**, **New customer** and **Account**. The search box and the **Save** and **Cancel** buttons sit just above that bar, within reach of your thumb.

## When it will not open or sign in

- **"Can't reach the control app"** in the installed app, or Chrome saying the site cannot be reached: Tailscale is off or not connected, or there is no signal. Connect Tailscale and tap **Try again**. If the server itself is down, see [../operations/monitoring.md](../operations/monitoring.md).
- **"Bad Request (400)":** the address typed is not one the app accepts. Use the tailnet address exactly; see [../operations/troubleshooting.md](../operations/troubleshooting.md).
- **"Forbidden (403)" after tapping Sign in:** the page was opened by an address other than the tailnet address, or it was left open so long that its form expired. Open the tailnet address again and sign in from a freshly loaded page.
- **"Your username or password is not right":** check the username and password, or ask the owner to reset the password as in Step 1.
- **No "Install" option in Chrome:** the page was not opened over `https://` at the tailnet address. Only that address can be installed.
