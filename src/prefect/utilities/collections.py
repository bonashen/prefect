"""
Utilities for extensions of and operations on Python collections.
"""
import itertools
from collections import OrderedDict, defaultdict
from collections.abc import Iterator as IteratorABC
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Hashable,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)
from unittest.mock import Mock

import pydantic

# Quote moved to `prefect.utilities.annotations` but preserved here for compatibility
from prefect.utilities.annotations import BaseAnnotation, Quote, quote, revisit  # noqa


class AutoEnum(str, Enum):
    """
    An enum class that automatically generates value from variable names.

    This guards against common errors where variable names are updated but values are
    not.

    In addition, because AutoEnums inherit from `str`, they are automatically
    JSON-serializable.

    See https://docs.python.org/3/library/enum.html#using-automatic-values

    Example:
        ```python
        class MyEnum(AutoEnum):
            RED = AutoEnum.auto() # equivalent to RED = 'RED'
            BLUE = AutoEnum.auto() # equivalent to BLUE = 'BLUE'
        ```
    """

    def _generate_next_value_(name, start, count, last_values):
        return name

    @staticmethod
    def auto():
        """
        Exposes `enum.auto()` to avoid requiring a second import to use `AutoEnum`
        """
        return auto()

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.value}"


KT = TypeVar("KT")
VT = TypeVar("VT")


def dict_to_flatdict(
    dct: Dict[KT, Union[Any, Dict[KT, Any]]], _parent: Tuple[KT, ...] = None
) -> Dict[Tuple[KT, ...], Any]:
    """Converts a (nested) dictionary to a flattened representation.

    Each key of the flat dict will be a CompoundKey tuple containing the "chain of keys"
    for the corresponding value.

    Args:
        dct (dict): The dictionary to flatten
        _parent (Tuple, optional): The current parent for recursion

    Returns:
        A flattened dict of the same type as dct
    """
    typ = cast(Type[Dict[Tuple[KT, ...], Any]], type(dct))
    items: List[Tuple[Tuple[KT, ...], Any]] = []
    parent = _parent or tuple()

    for k, v in dct.items():
        k_parent = tuple(parent + (k,))
        # if v is a non-empty dict, recurse
        if isinstance(v, dict) and v:
            items.extend(dict_to_flatdict(v, _parent=k_parent).items())
        else:
            items.append((k_parent, v))
    return typ(items)


def flatdict_to_dict(
    dct: Dict[Tuple[KT, ...], VT]
) -> Dict[KT, Union[VT, Dict[KT, VT]]]:
    """Converts a flattened dictionary back to a nested dictionary.

    Args:
        dct (dict): The dictionary to be nested. Each key should be a tuple of keys
            as generated by `dict_to_flatdict`

    Returns
        A nested dict of the same type as dct
    """
    typ = type(dct)
    result = cast(Dict[KT, Union[VT, Dict[KT, VT]]], typ())
    for key_tuple, value in dct.items():
        current_dict = result
        for prefix_key in key_tuple[:-1]:
            # Build nested dictionaries up for the current key tuple
            # Use `setdefault` in case the nested dict has already been created
            current_dict = current_dict.setdefault(prefix_key, typ())  # type: ignore
        # Set the value
        current_dict[key_tuple[-1]] = value

    return result


T = TypeVar("T")


def isiterable(obj: Any) -> bool:
    """
    Return a boolean indicating if an object is iterable.

    Excludes types that are iterable but typically used as singletons:
    - str
    - bytes
    """
    try:
        iter(obj)
    except TypeError:
        return False
    else:
        return not isinstance(obj, (str, bytes))


def ensure_iterable(obj: Union[T, Iterable[T]]) -> Iterable[T]:
    if isinstance(obj, Sequence) or isinstance(obj, Set):
        return obj
    obj = cast(T, obj)  # No longer in the iterable case
    return [obj]


def listrepr(objs: Iterable, sep=" ") -> str:
    return sep.join(repr(obj) for obj in objs)


def extract_instances(
    objects: Iterable,
    types: Union[Type[T], Tuple[Type[T], ...]] = object,
) -> Union[List[T], Dict[Type[T], T]]:
    """
    Extract objects from a file and returns a dict of type -> instances

    Args:
        objects: An iterable of objects
        types: A type or tuple of types to extract, defaults to all objects

    Returns:
        If a single type is given: a list of instances of that type
        If a tuple of types is given: a mapping of type to a list of instances
    """
    types = ensure_iterable(types)

    # Create a mapping of type -> instance from the exec values
    ret = defaultdict(list)

    for o in objects:
        # We iterate here so that the key is the passed type rather than type(o)
        for type_ in types:
            if isinstance(o, type_):
                ret[type_].append(o)

    if len(types) == 1:
        return ret[types[0]]

    return ret


def batched_iterable(iterable: Iterable[T], size: int) -> Iterator[Tuple[T, ...]]:
    """
    Yield batches of a certain size from an iterable

    Args:
        iterable (Iterable): An iterable
        size (int): The batch size to return

    Yields:
        tuple: A batch of the iterable
    """
    it = iter(iterable)
    while True:
        batch = tuple(itertools.islice(it, size))
        if not batch:
            break
        yield batch


def visit_collection(
    expr,
    visit_fn: Callable[[Any], Any],
    return_data: bool = False,
    max_depth: int = -1,
    context: Optional[dict] = None,
):
    """
    This function visits every element of an arbitrary Python collection. If an element
    is a Python collection, it will be visited recursively. If an element is not a
    collection, `visit_fn` will be called with the element. The return value of
    `visit_fn` can be used to alter the element if `return_data` is set.

    Note that when using `return_data` a copy of each collection is created to avoid
    mutating the original object. This may have significant performance penalities and
    should only be used if you intend to transform the collection.

    Supported types:
    - List
    - Tuple
    - Set
    - Dict (note: keys are also visited recursively)
    - Dataclass
    - Pydantic model
    - Prefect annotations

    Args:
        expr (Any): a Python object or expression
        visit_fn (Callable[[Any], Awaitable[Any]]): an async function that
            will be applied to every non-collection element of expr.
        return_data (bool): if `True`, a copy of `expr` containing data modified
            by `visit_fn` will be returned. This is slower than `return_data=False`
            (the default).
        max_depth: Controls the depth of recursive visitation. If set to zero, no
            recursion will occur. If set to a positive integer N, visitation will only
            descend to N layers deep. If set to any negative integer, no limit will be
            enforced and recursion will continue until terminal items are reached. By
            default, recursion is unlimited.
        context: An optional dictionary. If passed, the context will be sent to each
            call to the `visit_fn`. The context can be mutated by each visitor and will
            be available for later visits to expressions at the given depth. Values
            will not be available "up" a level from a given expression.
    """

    def visit_nested(expr):
        # Utility for a recursive call, preserving options and updating the depth.
        return visit_collection(
            expr,
            visit_fn=visit_fn,
            return_data=return_data,
            max_depth=max_depth - 1,
            # Copy the context on nested calls so it does not "propagate up"
            context=context.copy() if context is not None else None,
        )

    def visit_expression(expr):
        if context is not None:
            return visit_fn(expr, context)
        else:
            return visit_fn(expr)

    # Visit every expression
    result = visit_expression(expr)

    if return_data or isinstance(result, revisit):
        # Only mutate the expression while returning data, otherwise it could be null
        # An exception is made for the `revisit` annotation
        expr = result

    # Then, visit every child of the expression recursively

    # If we have reached the maximum depth, do not perform any recursion
    if max_depth == 0:
        return result if return_data else None

    # Get the expression type; treat iterators like lists
    typ = list if isinstance(expr, IteratorABC) else type(expr)
    typ = cast(type, typ)  # mypy treats this as 'object' otherwise and complains

    # Then visit every item in the expression if it is a collection
    if isinstance(expr, Mock):
        # Do not attempt to recurse into mock objects
        result = expr

    elif typ in (list, tuple, set):
        items = [visit_nested(o) for o in expr]
        result = typ(items) if return_data else None

    elif typ in (dict, OrderedDict):
        assert isinstance(expr, (dict, OrderedDict))  # typecheck assertion
        items = [(visit_nested(k), visit_nested(v)) for k, v in expr.items()]
        result = typ(items) if return_data else None

    elif is_dataclass(expr) and not isinstance(expr, type):
        values = [visit_nested(getattr(expr, f.name)) for f in fields(expr)]
        items = {field.name: value for field, value in zip(fields(expr), values)}
        result = typ(**items) if return_data else None

    elif isinstance(expr, pydantic.BaseModel):
        # NOTE: This implementation *does not* traverse private attributes
        # Pydantic does not expose extras in `__fields__` so we use `__fields_set__`
        # as well to get all of the relevant attributes
        model_fields = expr.__fields_set__.union(expr.__fields__)
        items = [visit_nested(getattr(expr, key)) for key in model_fields]

        if return_data:
            # Collect fields with aliases so reconstruction can use the correct field name
            aliases = {
                key: value.alias
                for key, value in expr.__fields__.items()
                if value.has_alias
            }

            model_instance = typ(
                **{
                    aliases.get(key) or key: value
                    for key, value in zip(model_fields, items)
                }
            )

            # Private attributes are not included in `__fields_set__` but we do not want
            # to drop them from the model so we restore them after constructing a new
            # model
            for attr in expr.__private_attributes__:
                # Use `object.__setattr__` to avoid errors on immutable models
                object.__setattr__(model_instance, attr, getattr(expr, attr))

            result = model_instance
        else:
            result = None

    elif isinstance(expr, revisit):
        # `revisit` is not rewrapped since it is a signal to this function
        result = visit_nested(expr.unwrap())

    elif isinstance(expr, BaseAnnotation):
        result = expr.rewrap(visit_nested(expr.unwrap()))

    else:
        result = result if return_data else None

    return result


def remove_nested_keys(keys_to_remove: List[Hashable], obj):
    """
    Recurses a dictionary returns a copy without all keys that match an entry in
    `key_to_remove`. Return `obj` unchanged if not a dictionary.

    Args:
        keys_to_remove: A list of keys to remove from obj obj: The object to remove keys
        from.

    Returns:
        `obj` without keys matching an entry in `keys_to_remove` if `obj` is a
        dictionary. `obj` if `obj` is not a dictionary.
    """
    if not isinstance(obj, dict):
        return obj
    return {
        key: remove_nested_keys(keys_to_remove, value)
        for key, value in obj.items()
        if key not in keys_to_remove
    }


def distinct(
    iterable: Iterable[T],
    key: Callable[[T], Any] = (lambda i: i),
) -> Generator[T, None, None]:
    seen: Set = set()
    for item in iterable:
        if key(item) in seen:
            continue
        seen.add(key(item))
        yield item
