"""Provider adapters. `get_parser` maps a stored payload's format to its parser."""

from quantlab.data.providers.base import PayloadParser, ProviderDataError
from quantlab.data.providers.csv_file import CSV_FORMAT_ID, CsvParser
from quantlab.data.providers.synthetic import SYNTHETIC_FORMAT_ID, SyntheticParser

_PARSERS: dict[str, PayloadParser] = {
    SYNTHETIC_FORMAT_ID: SyntheticParser(),
    CSV_FORMAT_ID: CsvParser(),
}


def get_parser(format_id: str) -> PayloadParser:
    try:
        return _PARSERS[format_id]
    except KeyError:
        raise ProviderDataError(f"no parser registered for format '{format_id}'") from None
