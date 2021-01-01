# Django REST Live

[![Documentation](https://readthedocs.org/projects/django-rest-live/badge/?version=latest)](https://django-rest-live.readthedocs.io/en/latest/?badge=latest)
[![CircleCI](https://circleci.com/gh/pennlabs/django-rest-live.svg?style=shield)](https://circleci.com/gh/pennlabs/django-rest-live)
[![Coverage Status](https://codecov.io/gh/pennlabs/django-rest-live/branch/master/graph/badge.svg)](https://codecov.io/gh/pennlabs/django-rest-live)
[![PyPi Package](https://img.shields.io/pypi/v/django-rest-live.svg)](https://pypi.org/project/django-rest-live/)

`django-rest-live` adds real-time subscriptions over websockets to [Django REST Framework](https://github.com/encode/django-rest-framework)
views by leveraging websocket support provided by [Django Channels](https://github.com/django/channels).

`django-rest-live` took initial inspiration from [this article by Kit La Touche](https://www.oddbird.net/2018/12/12/channels-and-drf/).
The goal of this project is to be as close as possible to a drop-in realtime solution for projects already
using Django REST Framework. 

Differently from projects like [`djangochannelsrestframework`](https://github.com/hishnash/djangochannelsrestframework),
`django-rest-live` does not aim to supplant REST Framework for performing CRUD actions through a REST API. Instead,
it is designed to be used in conjunction with HTTP REST endpoints. Clients should still use normal REST framework
endpoints generated by ViewSets and other API views to get initial data to populate a page, as well as any write-driven
behavior (`POST`, `PATCH`, `PUT`, `DELETE`). `django-rest-live` gets rid of the need for periodic polling GET
requests to for resource updates after page load.

