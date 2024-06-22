import traceback
from typing import TypeVar, Iterable


T = TypeVar("T")
SetOrVal = T | list[T]


def as_set(val: SetOrVal[T]) -> set[T]:
    if isinstance(val, Iterable) and not isinstance(val, str):
        return set(val)
    else:
        return {val}


def get_first_set_prop(old_loc, old_props: SetOrVal[str]):
    """Pops all old props and returns the first one that is set"""
    result = None
    for old_prop in as_set(old_props):
        old_value = old_loc.pop(old_prop, None)
        if old_value is not None:
            result = old_value
    return result


def upgrade_value(new_loc, new_prop: str, old_loc, old_props: SetOrVal[str], old_enum: list[str] = None):
    try:
        old_value = get_first_set_prop(old_loc, old_props)
        if old_value is None:
            return False
        if old_enum:
            assert isinstance(old_value, int)
            if old_value >= len(old_enum):
                raise ValueError(f"({old_value}) not in {old_enum}")
            old_value = old_enum[old_value]
            if getattr(new_loc, new_prop) == old_value:
                return False
            setattr(new_loc, new_prop, old_value)
        else:
            if new_loc.get(new_prop, None) == old_value:
                return False
            new_loc[new_prop] = old_value

        print(f'{new_prop} set to "{getattr(new_loc, new_prop)}"')
        return True
    except Exception as e:
        print(f"Failed to upgrade {new_prop} from old location {old_loc} with props {old_props}")
        traceback.print_exc()
        return False
