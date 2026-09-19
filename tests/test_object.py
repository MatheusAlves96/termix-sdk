from __future__ import annotations

import pytest

from termix_sdk._object import TermixObject


def test_attribute_and_item_access():
    host = TermixObject.construct_from({"id": 1, "name": "web-1", "ip": "10.0.0.1"})
    assert host.id == 1
    assert host["name"] == "web-1"
    assert host.ip == "10.0.0.1"


def test_missing_field_raises_attribute_error_with_known_fields():
    host = TermixObject.construct_from({"id": 1})
    with pytest.raises(AttributeError, match="name"):
        host.name


def test_field_named_like_a_dict_method_wins_over_the_method_meaning():
    # GET /releases/rss really does return a field literally named "items"
    # (spec/termix-openapi.json) — the field must win, not a bound
    # .items() method that would permanently shadow it.
    obj = TermixObject.construct_from({"items": ["a", "b"]})
    assert obj.items == ["a", "b"]
    assert obj["items"] == ["a", "b"]


def test_dict_method_shaped_name_with_no_matching_field_raises_helpful_error():
    obj = TermixObject.construct_from({"id": 1})
    with pytest.raises(AttributeError, match="to_dict"):
        obj.get


def test_construct_from_list_returns_list_of_objects():
    hosts = TermixObject.construct_from([{"id": 1}, {"id": 2}])
    assert isinstance(hosts, list)
    assert [h.id for h in hosts] == [1, 2]


def test_construct_from_nested_dict_recurses():
    obj = TermixObject.construct_from({"meta": {"total": 3}})
    assert isinstance(obj.meta, TermixObject)
    assert obj.meta.total == 3


def test_construct_from_nested_list_of_dicts_recurses():
    obj = TermixObject.construct_from({"items": [{"id": 1}, {"id": 2}]})
    assert all(isinstance(i, TermixObject) for i in obj.items)


def test_construct_from_scalar_passthrough():
    assert TermixObject.construct_from(None) is None
    assert TermixObject.construct_from("plain-string") == "plain-string"


def test_to_dict_recursive():
    obj = TermixObject.construct_from({"id": 1, "nested": {"a": 1}, "list": [{"b": 2}]})
    d = obj.to_dict()
    assert d == {"id": 1, "nested": {"a": 1}, "list": [{"b": 2}]}


def test_secrets_redacted_in_str_and_repr():
    host = TermixObject.construct_from({"id": 1, "password": "s3cr3t", "sudoPassword": "s3cr3t2"})
    text = str(host)
    assert "s3cr3t" not in text
    assert "s3cr3t2" not in text
    assert "<redacted>" in text
    assert "s3cr3t" not in repr(host)


def test_non_secret_fields_not_redacted():
    host = TermixObject.construct_from({"username": "alice"})
    assert "alice" in str(host)


def test_equality():
    a = TermixObject.construct_from({"id": 1})
    b = TermixObject.construct_from({"id": 1})
    c = TermixObject.construct_from({"id": 2})
    assert a == b
    assert a != c


def test_setattr_stores_as_field():
    obj = TermixObject()
    obj.foo = "bar"
    assert obj["foo"] == "bar"


def test_inner_class_types_dispatch():
    class Owner(TermixObject):
        pass

    class Host(TermixObject):
        _inner_class_types = {"owner": Owner}

    host = Host.construct_from({"id": 1, "owner": {"userId": "u1"}})
    assert isinstance(host, Host)
    assert isinstance(host.owner, Owner)
    assert host.owner.userId == "u1"
