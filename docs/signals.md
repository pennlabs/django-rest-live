# A note on Django signals
This package works by listening in on model lifecycle events sent off by Django's [signal dispatcher](https://docs.djangoproject.com/en/3.1/topics/signals/).
Specifically, the [`post_save`](https://docs.djangoproject.com/en/3.1/ref/signals/#post-save)
and [`post_delete`](https://docs.djangoproject.com/en/3.1/ref/signals/#post-delete) signals. This means that `django-rest-live`
can only pick up changes that Django knows about. Bulk operations, like `filter().update()`, `bulk_create`
and `bulk_delete` do not trigger Django's lifecycle signals, so updates will not be sent.
