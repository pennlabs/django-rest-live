# RealtimeMixin Reference

`rest_live.mixins.RealtimeMixin` marks a Django REST Framework
Generic APIView as realtime capable. Any subclass class of
[`rest_framework.generics.GenericAPIView`](https://www.django-rest-framework.org/api-guide/generic-views/#genericapiview)
can be used with `RealtimeMixin`, like `ListAPIView`, `RetrieveAPIView`, and `ModelViewSet`.

These are the View properties and methods used by the `RealtimeMixin`:

- `lookup_field` (defaults to `pk` in DRF)
- `queryset`
    * Even if `get_queryset()` is defined, `queryset` must
    also be defined so that the [`RealtimeRouter`](router.md)
    can determine the underlying model class at register-time.
    If you use `get_queryset` to dynamically filter the queryset
    in your view, you should also define an empty "sentinel" queryset
    on the view of the form `Model.queryset.none()`. This is
    what's recommended for other [parts of REST Framework](https://www.django-rest-framework.org/api-guide/permissions/#using-with-views-that-do-not-include-a-queryset-attribute)
    which require knowledge of a view's backing model.
- `get_serializer_class()` or `serializer_class`
- `permission_classes` or `get_permissions()`
