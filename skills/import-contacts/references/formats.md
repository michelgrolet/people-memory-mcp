# Import formats

## LinkedIn

Use the official Connections CSV. Expected fields include First Name, Last Name, URL, Email Address,
Company, Position, and Connected On. Some rows have no email, so similar names require review.

## Google Contacts

Use Google Contacts export CSV. Field names vary by locale. Map name, emails, phones, organization,
title, city, and country. Ignore notes and addresses unless the user explicitly wants them.

## WhatsApp

Use an official text export. Require the owner's display name so their own messages do not create a
person record. Import participants and interaction dates. Do not store message bodies by default.

## Other CSV or JSON

Inspect headers and at most five redacted rows. Propose mappings for name, identifier, organization,
role, location, relationship, and dates. Ask before importing unknown sensitive columns.
