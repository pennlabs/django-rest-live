# Testing
As of Django 3.1, you can write asynchronous tests in Django `TestCase`s. You can set up a test case by following
the snippet below, using the test communicator provided in `rest_live.testing.APICommunicator`.

## Sample TestCase

```python
from django.test import TransactionTestCase
from app.routing import application  # Replace this line with the import to your ASGI router.
from channels.db import database_sync_to_async
from rest_live.testing import APICommunicator

class MyTests(TransactionTestCase):
    async def test_subscribe(self):
        client = APICommunicator(application, "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
        await client.send_json_to(
            {
                "type": "subscribe",
                "id": 1337,
                "model": "app.Model",
                "action": "retrieve",
                "lookup_by": "1",
            }
        )
        self.assertTrue(await client.receive_nothing())
        await database_sync_to_async(Model.objects.create)(...)
        response = await client.receive_json_from()
        self.assertEqual(response, {
            "type": "broadcast",
            "id": 1337,
            "model": "app.Model",
            "instance": { "": "..." },
            "action": "CREATED",
        })
        await client.disconnect()
```

Since REST Live makes use of the database for its functionality, make sure to use `django.test.TransactionTestCase`
instead of `django.test.TestCase` so that database connections within the async test functions get cleaned up approprately.

Remember to wrap all ORM calls in the `database_sync_to_async` decorator as demonstrated in the above example. The ORM
is still fully synchronous, and the regular `sync_to_async` decorator does not properly clean up connections!

## setUp and tearDown
The normal `TestCase.setUp` and `TestCase.tearDown` methods run in different threads from the actual test itself,
and so they don't work for creating async objects like `WebsocketCommunicator`. REST Live comes with a decorator called
`@async_test` which will enable test cases to define lifecycle methods `asyncSetUp()` and `asyncTearDown()` to
run certain code before and after every test case decorated with `@async_test`. Here is an example:

```python
...
from rest_live.testing import APICommunicator, async_test
class MyTests(TransactionTestCase):
    
    async def asyncSetUp(self):
        self.client = APICommunicator(application, "/ws/subscribe/")
        connected, _ = await self.client.connect()
        self.assertTrue(connected)
    
    async def asyncTearDown(self):
        await self.client.disconnect()
        
    @async_test
    async def test_subscribe(self):
        ...  # a new connection has been opened and is accessible in `self.client`
```

## Authentication
Make sure to follow the below pattern if you use `request.user` or `request.session` anywhere in your View code.

Authentication in unit tests for django channels is a bit tricky, but the utility that `rest_live` provides
is based on this [github issue comment](https://github.com/django/channels/issues/903#issuecomment-365735926).

The `WebsocketCommunicator` class can take HTTP headers as part of its constructor. In order to open a connection
as a logged-in user, you can use `rest_live.testing.get_headers_for_user`:

```python
from rest_live.testing import get_headers_for_user

user = await database_sync_to_async(User.objects.create_user)(username="test")
headers = await get_headers_for_user(user)
client = APICommunicator(appliction, "/ws/subscribe/", headers)
...
```
