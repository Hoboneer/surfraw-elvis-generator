# Copyright 2019 Gabriel Lisaca
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import sys
import os
import re
from itertools import chain
from collections import namedtuple
from functools import wraps
from os import EX_OK, EX_SOFTWARE, EX_OSERR, EX_USAGE
from jinja2 import PackageLoader, Environment


def get_parser():
    parser = argparse.ArgumentParser(description="generate an elvis for surfraw")
    parser.add_argument("name", help="name for the elvis")
    parser.add_argument(
        "base_url",
        help="the url to show in the description and is the url opened when no search terms are passed, with no protocol",
    )
    parser.add_argument(
        "search_url",
        help="the url to append arguments to, with the query parameters opened and no protocol (automatically set to 'https')",
    )
    parser.add_argument(
        "--description",
        help="description for the elvis, excluding the domain name in parentheses",
    )
    parser.add_argument(
        "--insecure", action="store_true", help="use 'http' instead of 'https'"
    )
    # Option generation
    parser.add_argument(
        "--flag",
        "-F",
        action="append",
        default=[],
        type=parse_flag_option,
        dest="flags",
        metavar="FLAG_NAME:FLAG_TARGET:YES_OR_NO",
        help="specify a flag for the elvis",
    )
    parser.add_argument(
        "--yes-no",
        "-Y",
        action="append",
        default=[],
        type=parse_bool_option,
        dest="bools",
        metavar="VARIABLE_NAME:DEFAULT_YES_OR_NO",
        help="specify a yes or no option for the elvis",
    )
    parser.add_argument(
        "--enum",
        "-E",
        action="append",
        default=[],
        type=parse_enum_option,
        dest="enums",
        metavar="VARIABLE_NAME:DEFAULT_VALUE:VAL1,VAL2,...",
        help="specify an option with an argument from a range of values",
    )
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        type=parse_alias_option,
        dest="aliases",
        metavar="ALIAS_NAME:ALIAS_TARGET",
        help="make an alias to another defined option",
    )
    parser.add_argument(
        "--map",
        "-M",
        action="append",
        default=[],
        type=parse_mapping_option,
        dest="mappings",
        metavar="VARIABLE_NAME:PARAMETER",
        help="map a variable to a URL parameter",
    )
    parser.add_argument(
        "--query-parameter",
        "-Q",
        type=parse_query_parameter,
        help="define the parameter for the query arguments; needed with --map",
    )
    return parser


# Validity checks

# This is purposely not in the full range of shell variable names because I am
# trying to encourage a particular naming convention. That is,
# `SURFRAW_elvisname_onewordvar` is what the script would generate.
VALID_SURFRAW_VAR_NAME = re.compile("^[a-z]+$")


def is_valid_name(name):
    return VALID_SURFRAW_VAR_NAME.fullmatch(name)


# This seems to be a spec that would satisfy most websites.
VALID_URL_PARAM = re.compile("^[A-Za-z0-9_]+$")


def is_valid_url_parameter(url_param):
    return VALID_URL_PARAM.fullmatch(url_param)


# TODO: Should the yes-no option take the other forms?
# TRUE_WORDS = {"yes", "on", "1"}
# FALSE_WORDS = {"no", "off", "0"}
TRUE_WORDS = {"yes"}
FALSE_WORDS = {"no"}
BOOL_WORDS = TRUE_WORDS | FALSE_WORDS


def is_valid_bool(bool_arg):
    return bool_arg in BOOL_WORDS


# Parse errors


def insufficient_spec_parts(arg, num_required):
    raise argparse.ArgumentTypeError(
        f"option arg '{arg}' needs at least {num_required} colon-delimited parts"
    )


def invalid_name(name):
    raise argparse.ArgumentTypeError(
        f"name '{name}' is an invalid variable name for an elvis"
    )


def invalid_bool(bool_arg):
    valid_bools = ", ".join(sorted(BOOL_WORDS))
    raise argparse.ArgumentTypeError(
        f"bool '{bool_arg}' must be one of the following: {valid_bools}"
    )


def invalid_url_parameter(url_param):
    raise argparse.ArgumentTypeError(f"'{url_param}' is an invalid URL parameter")


# Parsers


def parse_args(validators):
    """Decorator to validate args of argument spec for generated elvis.

    Raises `argparse.ArgumentTypeError` when invalid, otherwise calls decorated
    function with validated arguments, returning its value.
    """

    def wrapper(func):
        # Only takes positional args.
        @wraps(func)
        def validate_args_wrapper(raw_arg):
            args = raw_arg.split(":")
            valid_args = []
            for i, valid_or_fail_func in enumerate(validators):
                try:
                    arg = args[i]
                except IndexError:
                    # Raise `argparse.ArgumentTypeError`
                    insufficient_spec_parts(raw_arg, num_required=len(validators))
                else:
                    # Raise `argparse.ArgumentTypeError` if invalid arg.
                    valid_or_fail_func(arg)
                    valid_args.append(arg)
            return func(*valid_args)

        return validate_args_wrapper

    return wrapper


def validate_name(name):
    if not is_valid_name(name):
        invalid_name(name)


def validate_bool(bool_):
    if not is_valid_bool(bool_):
        invalid_bool(bool_)


def validate_url_parameter(url_param):
    if not is_valid_url_parameter(url_param):
        invalid_url_parameter(url_param)


def no_validation(_):
    pass


class FlagOption:
    def __init__(self, name, target, value):
        self.name = name
        self.target = target
        self.value = value


BoolOption = namedtuple("BoolOption", ["name", "default"])
EnumOption = namedtuple("EnumOption", ["name", "default", "values"])


class AliasOption:
    def __init__(self, name, target):
        self.name = name
        self.target = target


MappingOption = namedtuple("MappingOption", ["variable", "parameter"])


@parse_args([validate_name, validate_name, validate_bool])
def parse_flag_option(name, target, value):
    """Check a flag option, requiring three colon-delimited parts."""
    return FlagOption(name, target, value)


@parse_args([validate_name, validate_bool])
def parse_bool_option(name, default):
    """Check a yes-no option, requiring two colon-delimited parts."""
    return BoolOption(name, default)


# Third argument is validated inside the function since it needs access to
# other arguments.
@parse_args([validate_name, validate_name, no_validation])
def parse_enum_option(name, default, orig_values):
    """Check an enum option, requiring three colon-delimited parts.

    The default value (part 2) *must* be a value in the third part.
    """
    # Check validity of values.
    values = orig_values.split(",")
    for val in values:
        if not is_valid_name(val):
            invalid_name(val)

    # Ensure `default` is among `values`.
    if default not in values:
        raise argparse.ArgumentTypeError(
            f"default value '{default}' must be within '{orig_values}'"
        )

    return EnumOption(name, default, values)


# NOTE: Aliases are useful since they would result in the target and its
# aliases to be displayed together in the help output.
@parse_args([validate_name, validate_name])
def parse_alias_option(name, target):
    """Make an alias to another option.

    NOTE: This function does *not* check whether the alias points to a valid
    option. It needs to be checked elsewhere since this does not have access to
    the parser.
    """
    return AliasOption(name, target)


@parse_args([validate_name, validate_url_parameter])
def parse_mapping_option(variable, parameter):
    return MappingOption(variable, parameter)


@parse_args([validate_url_parameter])
def parse_query_parameter(param):
    return param


# Taken from this stackoverflow answer:
#   https://stackoverflow.com/questions/12791997/how-do-you-do-a-simple-chmod-x-from-within-python/30463972#30463972
def make_executable(path):
    mode = os.stat(path).st_mode
    mode |= (mode & 0o444) >> 2  # copy R bits to X
    os.chmod(path, mode)


class OptionResolutionError(Exception):
    pass


def resolve_aliases(args):
    # TODO: What to do about naming conflicts?
    # Order is important! (Why?)
    options = [*chain(args.flags, args.bools, args.enums)]
    for alias in args.aliases:
        for option in options:
            if alias.target == option.name:
                alias.target = option
                break
        else:
            raise OptionResolutionError(
                f"alias '{alias.name}' does not target any existing option"
            )


def resolve_flags(args):
    # TODO: Allow flags to be shorthand for passing the value of any bool or
    # enum option.
    options = args.bools
    for flag in args.flags:
        for option in options:
            if flag.target == option.name:
                flag.target = option
                break
        else:
            raise OptionResolutionError(
                f"flag '{flag.name}' does not target any existing option"
            )


def resolve_mappings(args):
    options = list(chain(args.bools, args.enums))
    for mapping in args.mappings:
        for option in options:
            if mapping.variable == option.name:
                # Mappings don't get modified.
                break
        else:
            raise OptionResolutionError(
                f"URL parameter '{mapping.parameter}' does not target any existing variable"
            )


def make_namespace(prefix):
    def prefixer(name):
        return f"{prefix}_{name}"

    return prefixer


def generate_elvis(args):
    options = (args.flags, args.bools, args.enums, args.aliases)
    env = Environment(
        loader=PackageLoader("surfraw_tools"), trim_blocks=True, lstrip_blocks=True
    )

    # Add functions to jinja template
    env.globals["namespace"] = make_namespace(f"SURFRAW_{args.name}")
    env.globals["any_options_defined"] = lambda: any(
        len(option_container) for option_container in options
    )
    env.tests["flag_option"] = lambda x: isinstance(x, FlagOption)
    env.tests["bool_option"] = lambda x: isinstance(x, BoolOption)
    env.tests["enum_option"] = lambda x: isinstance(x, EnumOption)

    ELVIS_TEMPLATE = env.get_template("elvis.in")

    return ELVIS_TEMPLATE.render(
        name=args.name,
        description=args.description,
        base_url=args.base_url,
        search_url=args.search_url,
        options=options,
        # Options to generate
        flags=args.flags,
        bools=args.bools,
        enums=args.enums,
        aliases=args.aliases,
        # URL parameters
        mappings=args.mappings,
        query_parameter=args.query_parameter,
    )


def main(args=None):
    """Main program to generate surfraw elvi.

    Exit codes correspond to the distro's `sysexits.h` file, which are the
    exit codes prefixed "EX_".
    """
    if args is None:
        args = get_parser().parse_args()

    if args.description is None:
        args.description = f"Search {args.name} ({args.base_url})"
    else:
        args.description += f" ({args.base_url})"

    if args.insecure:
        # Is this the right term?
        url_scheme = "http"
    else:
        url_scheme = "https"

    args.base_url = f"{url_scheme}://{args.base_url}"
    args.search_url = f"{url_scheme}://{args.search_url}"

    try:
        resolve_aliases(args)
        resolve_flags(args)
        resolve_mappings(args)
    except OptionResolutionError as e:
        print(e, file=sys.stderr)
        return EX_USAGE

    if len(args.mappings) > 0 and args.query_parameter is None:
        print(
            "mapping variables without a defined --query-parameter is forbidden",
            file=sys.stderr,
        )
        # TODO: Use proper exit code.
        return EX_USAGE

    # Generate the elvis.
    try:
        elvis_program = generate_elvis(args)
    except Exception as e:
        # Ensure that the correct exit status is returned.
        print(e, file=sys.stderr)
        return EX_SOFTWARE

    try:
        with open(args.name, "w") as f:
            f.write(elvis_program)
        make_executable(args.name)
    except OSError:
        # I'm not sure if this is the correct exit code, and if the two
        # actions above should be separated.
        return EX_OSERR
    return EX_OK
