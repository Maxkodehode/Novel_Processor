# Diagnosis 1 — ScribbleHub Scraper Failure

**Date**: 2026-05-13 17:31

## Static HTML Analysis
- `li.toc_w` count: 15
- Chapter badge (`span.cnt_toc`): 118

## JS State
- `toc_fic_show_all`: function
- `ajaxurl`: NOT DEFINED
- `jQuery`: 3.2.0
- `simplePagination`: False

## AJAX Test
- Chapters after `toc_fic_show_all()`: 15
- Network log: ['POST https://www.scribblehub.com/wp-admin/admin-ajax.php', 'RESP 403 https://www.scribblehub.com/wp-admin/admin-ajax.php']

**CONCLUSION**: `toc_fic_show_all()` did NOT load more chapters. AJAX is blocked.
