"""
Core sanitiation functions that accept report-specific elements
"""

from typing import Callable, Dict, List

from avwx.parsing.core import dedupe, is_variable_wind_direction, is_wind
from avwx.structs import Sanitization
from .cleaners.base import (
    CleanerListType,
    CleanItem,
    RemoveItem,
    SplitItem,
    CombineItems,
)
from .cleaners.cloud import separate_cloud_layers
from .cleaners.wind import sanitize_wind


def sanitize_string_with(
    replacements: Dict[str, str]
) -> Callable[[str, Sanitization], str]:
    """Returns a function to sanitize the report string with a given list of replacements"""

    def sanitize_report_string(text: str, sans: Sanitization) -> str:
        """Provides sanitization for operations that work better when the report is a string"""
        text = text.upper().rstrip("=")
        if len(text) < 4:
            return text
        # Standardize whitespace
        text = " ".join(text.split())
        # Prevent changes to station ID
        stid, text = text[:4], text[4:]
        # Replace invalid key-value pairs
        for key, rep in replacements.items():
            if key in text:
                text = text.replace(key, rep)
                sans.log(key, rep)
        separated = separate_cloud_layers(text)
        if text != separated:
            sans.extra_spaces_needed = True
        return stid + separated

    return sanitize_report_string


def sanitize_list_with(
    cleaners: CleanerListType,
) -> Callable[[List[str], Sanitization], List[str]]:
    """Returns a function to sanitize the report list with a given list of cleaners"""
    _cleaners = [o() for o in cleaners]

    def sanitize_report_list(wxdata: List[str], sans: Sanitization) -> List[str]:
        """Provides sanitization for operations that work better when the report is a list"""
        for i, item in reversed(list(enumerate(wxdata))):
            for cleaner in _cleaners:
                # TODO: Py3.10 change to match/case on type
                if isinstance(cleaner, CombineItems):
                    if i and cleaner.can_handle(wxdata[i - 1], item):
                        wxdata[i - 1] += wxdata.pop(i)
                        sans.extra_spaces_found = True
                        if cleaner.should_break:
                            break
                elif isinstance(cleaner, SplitItem):
                    if index := cleaner.split_at(item):
                        wxdata.insert(i + 1, item[index:])
                        wxdata[i] = item[:index]
                        sans.extra_spaces_needed = True
                        if cleaner.should_break:
                            break
                elif cleaner.can_handle(item):
                    if isinstance(cleaner, RemoveItem):
                        sans.log(wxdata.pop(i))
                    elif isinstance(cleaner, CleanItem):
                        cleaned = cleaner.clean(item)
                        wxdata[i] = cleaned
                        sans.log(item, cleaned)
                    if cleaner.should_break:
                        break

        # TODO: Replace with above syntax after testing?
        # May wish to keep since some elements could be checked after space needed...but so could the others?

        # Check for wind sanitization
        for i, item in enumerate(wxdata):
            # Skip Station
            if i == 0:
                continue
            if is_variable_wind_direction(item):
                replaced = item[:7]
                wxdata[i] = replaced
                sans.log(item, replaced)
                continue
            possible_wind = sanitize_wind(item)
            if is_wind(possible_wind):
                if item != possible_wind:
                    sans.log(item, possible_wind)
                wxdata[i] = possible_wind

        # Strip extra characters before dedupe
        stripped = [i.strip("./\\") for i in wxdata]
        if wxdata != stripped:
            sans.log_list(wxdata, stripped)
        deduped = dedupe(stripped, only_neighbors=True)
        if len(deduped) != len(wxdata):
            sans.duplicates_found = True
        return deduped

    return sanitize_report_list
