from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, List, TypeVar, cast

if TYPE_CHECKING:
    from typing_extensions import Final


class OptionParseError(Exception):
    pass


class OptionResolutionError(Exception):
    pass


# NAME

# This is purposely not in the full range of shell variable names because I am
# trying to encourage a particular naming convention. That is,
# `SURFRAW_elvisname_onewordvar` is what the script would generate.
_VALID_SURFRAW_VAR_NAME: Final = re.compile("^[a-z]+$")


def validate_name(name: str) -> str:
    if not _VALID_SURFRAW_VAR_NAME.fullmatch(name):
        raise OptionParseError(
            f"name '{name}' is an invalid variable name for an elvis"
        )
    return name


# YES-NO

# TODO: Should the yes-no option take the other forms?
# TRUE_WORDS = {"yes", "on", "1"}
# FALSE_WORDS = {"no", "off", "0"}
_TRUE_WORDS: Final = {"yes"}
_FALSE_WORDS: Final = {"no"}
_BOOL_WORDS: Final = _TRUE_WORDS | _FALSE_WORDS


def validate_bool(bool_: str) -> str:
    if bool_ not in _BOOL_WORDS:
        valid_bools = ", ".join(sorted(_BOOL_WORDS))
        raise OptionParseError(
            f"bool '{bool_}' must be one of the following: {valid_bools}"
        )
    return bool_


def parse_bool(bool_: str) -> bool:
    if bool_ in _TRUE_WORDS:
        return True
    elif bool_ in _FALSE_WORDS:
        return False
    else:
        valid_bools = ", ".join(sorted(_BOOL_WORDS))
        raise OptionParseError(
            f"bool '{bool_}' must be one of the following: {valid_bools}"
        )


# OPTION TYPES is defined elsewhere to avoid circular imports.

# ENUM VALUES

_VALID_ENUM_VALUE_STR: Final = "^[a-z0-9][a-z0-9_+-]*$"
_VALID_ENUM_VALUE: Final = re.compile(_VALID_ENUM_VALUE_STR)


def validate_enum_value(value: str) -> str:
    if not _VALID_ENUM_VALUE.fullmatch(value):
        raise OptionParseError(
            f"enum value '{value}' must match the regex '{_VALID_ENUM_VALUE_STR}'"
        )
    return value


# MISC.


def no_validation(arg: str) -> str:
    return arg


T = TypeVar("T")


def list_of(validator: Callable[[str], T]) -> Callable[[str], List[T]]:
    def list_validator(arg: str) -> List[T]:
        if arg == "":
            return []
        values = arg.split(",")
        # In case the validators return a different object from its input (i.e., parsers).
        for i, value in enumerate(values):
            # Mutating it is fine here.
            values[i] = validator(value)  # type: ignore
        return cast(List[T], values)

    return list_validator
