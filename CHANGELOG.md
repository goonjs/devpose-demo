# Changelog

## devpose-demo v0.1.0

**Release date:** 2026-10-05 · **Release type:** Minor · **Previous version:** -

## Summary

This release adds a farewell message and an orders table, and makes the greeting more tolerant of extra spaces in names.

## Highlights

- New farewell message in the demo app
- Greetings now ignore leading and trailing spaces in names
- New orders table for the upcoming ordering feature

## New

- add farewell and orders table (#1) (app)

## Maintenance

- bootstrap demo baseline (repo)

## Upgrade notes

- Set the new environment variable `DEMO_API_URL` in every environment before deploying.
- Run database migration `001_create_orders.sql` before the deploy. It only adds a new table, so the previous version keeps working.

## Contributors

- Chalat
- Chalat Luprasit

**Full changelog:** -

