import decimal
import json
import os
from datetime import datetime

import pytest

from ocpp.exceptions import (
    FormatViolationError,
    NotImplementedError,
    PropertyConstraintViolationError,
    ProtocolError,
    TypeConstraintViolationError,
    UnknownCallErrorCodeError,
    ValidationError,
)
from ocpp.messages import (
    Call,
    CallError,
    CallResult,
    OCPPVersion,
    SchemaValidator,
    _DecimalEncoder,
    _validators,
    unpack,
    validate_payload,
)
from ocpp.v16.enums import Action

v16_validator = SchemaValidator(ocpp_version=OCPPVersion.v16)
v20_validator = SchemaValidator(ocpp_version=OCPPVersion.v20)


def test_unpack_with_invalid_json():
    """
    Test that correct exception is raised when unpack is called with invalid
    JSON.
    """
    with pytest.raises(FormatViolationError):
        unpack(b"\x01")


def test_unpack_without_jsonified_list():
    """
    OCPP messages are JSONified lists. This test make sure that the correct
    exception is raised when input is not a JSONified list.
    """
    with pytest.raises(ProtocolError):
        unpack(json.dumps("3"))


def test_unpack_without_message_type_id_in_json():
    """
    OCPP must contain the MessageTypeID as first element of the message.
    This test validates if correct exception is raised when this is not
    the case
    """
    with pytest.raises(ProtocolError):
        unpack(json.dumps([]))


def test_unpack_with_invalid_message_type_id_in_json():
    """
    OCPP messages only have 3 valid values for MessageTypeID, that is the first
    element of the OCPP message. This test validates that correct exception is
    raised when this value is invalid.
    """
    with pytest.raises(PropertyConstraintViolationError):
        unpack(json.dumps([5, 1]))


def test_get_validator_with_valid_name():
    """
    Test if correct validator is returned and if validator is added to cache.
    """
    _validators.clear()
    schema = v16_validator.get_schema_for_call(action="Reset")

    assert schema == list(_validators.values())[0]
    assert schema.schema == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "ResetRequest",
        "type": "object",
        "properties": {
            "type": {
                "additionalProperties": False,
                "type": "string",
                "enum": ["Hard", "Soft"],
            }
        },
        "additionalProperties": False,
        "required": ["type"],
    }


def test_get_validator_with_invalid_name():
    """
    Test if OSError is raised when schema validation file cannnot be found.
    """
    with pytest.raises(OSError):
        v16_validator.get_schema_for_call(action="non-existing")


def test_validate_set_charging_profile_payload():
    """ " Test if payloads with floats are validated correctly.

    This test uses the value of 21.4, which is internally represented as
    21.39999999999999857891452847979962825775146484375.
    You can verify this using `decimal.Decimal(21.4)`
    """
    message = Call(
        unique_id="1234",
        action="SetChargingProfile",
        payload={
            "connectorId": 1,
            "csChargingProfiles": {
                "chargingProfileId": 1,
                "stackLevel": 0,
                "chargingProfilePurpose": "TxProfile",
                "chargingProfileKind": "Relative",
                "chargingSchedule": {
                    "chargingRateUnit": "A",
                    "chargingSchedulePeriod": [{"startPeriod": 0, "limit": 21.4}],
                },
                "transactionId": 123456789,
            },
        },
    )

    validate_payload(message, schema_validator=v16_validator)


def test_validate_get_composite_profile_payload():
    """ " Test if payloads with floats are validated correctly.

    This test uses the value of 15.2, which is internally represented as
    15.19999999999999857891452847979962825775146484375.
    You can verify this using `decimal.Decimal(15.2)`
    """
    message = CallResult(
        unique_id="1234",
        action="GetCompositeSchedule",
        payload={
            "status": "Accepted",
            "connectorId": 1,
            "scheduleStart": "2021-06-15T14:01:32Z",
            "chargingSchedule": {
                "duration": 60,
                "chargingRateUnit": "A",
                "chargingSchedulePeriod": [{"startPeriod": 0, "limit": 15.2}],
            },
        },
    )

    validate_payload(message, schema_validator=v16_validator)


@pytest.mark.parametrize("validator", [v16_validator, v20_validator])
def test_validate_payload_with_valid_payload(validator):
    """
    Test if validate_payload doesn't return any exceptions when it's
    validating a valid payload.
    """
    message = CallResult(
        unique_id="1234",
        action="Heartbeat",
        payload={"currentTime": datetime.now().isoformat()},
    )

    validate_payload(message, schema_validator=validator)


def test_validate_payload_with_invalid_additional_properties_payload():
    """
    Test if validate_payload raises FormatViolationError when validation of
    payload with unrequested properties fails.
    """
    message = CallResult(
        unique_id="1234",
        action="Heartbeat",
        payload={"invalid_key": True},
    )

    with pytest.raises(FormatViolationError):
        validate_payload(message, schema_validator=v16_validator)


def test_validate_payload_with_invalid_type_payload():
    """
    Test if validate_payload raises TypeConstraintViolationError when
    validation of payload with mismatched type fails.
    """
    message = Call(
        unique_id="1234",
        action="StartTransaction",
        payload={
            "connectorId": 1,
            "idTag": "okTag",
            "meterStart": "invalid_type",
            "timestamp": "2022-01-25T19:18:30.018Z",
        },
    )

    with pytest.raises(TypeConstraintViolationError):
        validate_payload(message, schema_validator=v16_validator)


def test_validate_payload_with_invalid_missing_property_payload():
    """
    Test if validate_payload raises ProtocolError when validation of
    payload with missing properties fails.
    """
    message = Call(
        unique_id="1234",
        action="StartTransaction",
        payload={
            "connectorId": 1,
            "idTag": "okTag",
            # meterStart is purposely missing
            "timestamp": "2022-01-25T19:18:30.018Z",
        },
    )

    with pytest.raises(ProtocolError):
        validate_payload(message, schema_validator=v16_validator)


def test_validate_payload_with_invalid_message_type_id():
    """
    Test if validate_payload raises ValidationError when it is called with
    a message type id other than 2, Call, or 3, CallError.
    """
    with pytest.raises(ValidationError):
        validate_payload(dict(), schema_validator=v16_validator)


def test_validate_payload_with_non_existing_schema():
    """
    Test if correct exception is raised when a validation schema cannot be
    found.
    """
    message = CallResult(
        unique_id="1234",
        action="MagicSpell",
        payload={"invalid_key": True},
    )

    with pytest.raises(NotImplementedError):
        validate_payload(message, schema_validator=v16_validator)


def test_call_error_representation():
    call = CallError(
        unique_id=1,
        error_code="GenericError",
        error_description="Some message",
        error_details={},
    )

    assert (
        str(call) == "<CallError - unique_id=1, error_code=GenericError, "
        "error_description=Some message, error_details={}>"
    )


def test_call_representation():
    call = Call(unique_id="1", action=Action.Heartbeat, payload={})

    assert str(call) == "<Call - unique_id=1, action=Heartbeat, payload={}>"


def test_call_result_representation():
    call = CallResult(
        unique_id="1", action=Action.Authorize, payload={"status": "Accepted"}
    )

    assert (
        str(call) == "<CallResult - unique_id=1, action=Authorize, payload={'status': "
        "'Accepted'}>"
    )


def test_creating_exception_from_call_error():
    call_error = CallError(
        unique_id="1337",
        error_code="ProtocolError",
        error_description="Something went wrong",
        error_details="Some details about the error",
    )

    assert call_error.to_exception() == ProtocolError(
        description="Something went wrong", details="Some details about the error"
    )


def test_creating_exception_from_call_error_with_unknown_error_code():
    call_error = CallError(
        unique_id="1337",
        error_code="418",
        error_description="I'm a teapot",
    )

    with pytest.raises(UnknownCallErrorCodeError):
        call_error.to_exception()


def test_serializing_decimal():
    assert json.dumps([decimal.Decimal(2.000001)], cls=_DecimalEncoder) == "[2.0]"


def test_validate_meter_values_hertz():
    """
    Tests that a unit of measure called "Hertz" is permitted in validation.
    This was missing from the original 1.6 spec, but was added as an errata
    (see the OCPP 1.6 Errata sheet, v4.0 Release, 2019-10-23, page 34).
    """
    message = Call(
        unique_id="1234",
        action="MeterValues",
        payload={
            "connectorId": 1,
            "transactionId": 123456789,
            "meterValue": [
                {
                    "timestamp": "2020-02-21T13:48:45.459756Z",
                    "sampledValue": [
                        {
                            "value": "50.0",
                            "measurand": "Frequency",
                            "unit": "Hertz",
                        }
                    ],
                }
            ],
        },
    )

    validate_payload(message, schema_validator=v16_validator)


def test_validate_set_maxlength_violation_payload():
    """
    Test if payloads that violate maxLength raise a
    TypeConstraintViolationError
    """
    message = Call(
        unique_id="1234",
        action="StartTransaction",
        payload={
            "idTag": "012345678901234567890",
            "connectorId": 1,
        },
    )

    with pytest.raises(TypeConstraintViolationError):
        validate_payload(message, schema_validator=v16_validator)


def test_custom_schema_validation():
    message = Call(
        unique_id="1234",
        action="Heartbeat",
        payload={},
    )

    path = os.getcwd() + "/ocpp/v201/schemas"

    validator = SchemaValidator(ocpp_version=OCPPVersion.v201, path_to_schemas=path)
    validate_payload(message=message, schema_validator=validator)
