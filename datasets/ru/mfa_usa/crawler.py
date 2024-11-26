import re

from lxml import html
from normality import collapse_spaces
from rigour.mime.types import HTML

from zavod import Context
from zavod import helpers as h

# Used to match names in first cell in Cyrillic and Latin script, e.g. "Барак ОБАМА (Barack Hussein Obama II)"
REGEX_NAME = re.compile(r"(?P<name_cyrillic>.+)\s\((?P<name_latin>.+)\)")
# Use to match the "as of" date, which is buried somewhere in a nondescript <span>
REGEX_PUBLISHED_DATE = re.compile(r"по состоянию на (?P<date>\d+.\d+.\d+)")


def crawl(context: Context):
    path = context.fetch_resource("source.html", context.data_url)
    context.export_resource(path, HTML, title=context.SOURCE_TITLE)
    with open(path, "r") as fh:
        doc = html.parse(fh)

    published_date = None
    published_date_match = REGEX_PUBLISHED_DATE.search(doc.getroot().text_content())
    if published_date_match:
        published_date = published_date_match.groupdict()["date"]
    else:
        context.log.warning("Could not find published date in page")

    table = doc.find(".//table")
    # No table headers, so go through table without helpers
    for row in table.findall(".//tr"):
        crawl_row(context, row, published_date)


def crawl_row(context: Context, row: html.Element, published_date: str):
    cells = row.findall("./td")

    # Skip section header rows (one section per letter of the alphabet)
    if len(cells) != 4:
        # If it's not just a one-letter section heading, we don't know what this is
        if len(row.text_content().strip()) != 1:
            context.log.warning("Skipping row with unexpected format", row_text=row.text_content())
        return

    name_cell_text = collapse_spaces(cells[1].text_content())
    name_match = REGEX_NAME.match(name_cell_text)
    if name_match is None:
        context.log.warning("Name cell text has unexpected format", name_cell_text=name_cell_text)
        return
    name_cyrillic = name_match.groupdict()["name_cyrillic"]
    name_latin = name_match.groupdict()["name_latin"]

    entity = context.make("Person")
    entity.id = context.make_id(name_latin)
    entity.add("name", name_latin, lang="eng")
    entity.add("name", name_cyrillic, lang="rus")
    # TODO(Leon Handreke): Is this always a position? In some cases, it's just "U.S. citizen" ("гражданин США")
    # Maybe there is a more appropriate property for this?
    entity.add("position", cells[3].text_content())
    # By definition, all people on this list have US citizenship
    entity.add("citizenship", "us")

    # Do not use cell[0] as the key param or the authorityId here because it seems to just be a consecutive number
    # in the alphabetically-sorted table that changes when new entries are inserted.
    sanction = h.make_sanction(context, entity)
    # TODO(Leon Handreke): Is this really the right prop, since this is the date of the publication of the whole list,
    # rather than the date of first inclusion of the person on that list?
    h.apply_date(sanction, "listingDate", published_date)

    context.emit(entity, target=True)
    context.emit(sanction)
