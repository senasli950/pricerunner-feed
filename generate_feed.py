import os
import re
import html
import requests
import csv
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom


SHOPIFY_STORE = "it3u3i-5e.myshopify.com"
ACCESS_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]

API_VERSION = "2025-01"

URL = (
    f"https://{SHOPIFY_STORE}"
    f"/admin/api/{API_VERSION}/graphql.json"
)

HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

GOOGLE_SHEET_ID = "14xegQdHjQBytqo-k2E6N8H3AeCqRqvEJ3BmSTZgTQRY"

GOOGLE_SHEET_NAME = "GTIN"

GOOGLE_SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={GOOGLE_SHEET_NAME}"
)

BRAND_RULES = [
    ("xbox game pass", "Microsoft"),
    ("microsoft office", "Microsoft"),
    ("office 365", "Microsoft"),
    ("office 2024", "Microsoft"),
    ("office 2021", "Microsoft"),
    ("office 2019", "Microsoft"),
    ("office 2016", "Microsoft"),
    ("office 2013", "Microsoft"),
    ("windows server", "Microsoft"),
    ("windows 11", "Microsoft"),
    ("windows 10", "Microsoft"),
    ("windows 7", "Microsoft"),
    ("windows 8", "Microsoft"),
    ("windows", "Microsoft"),
    ("minecraft", "Microsoft"),

    ("kaspersky", "Kaspersky"),
    ("norton", "Norton"),
    ("mcafee", "McAfee"),
    ("avast", "Avast"),
    ("avg", "AVG"),
    ("bitdefender", "Bitdefender"),
    ("eset", "ESET"),
    ("surfshark", "Surfshark"),
    ("nordvpn", "NordVPN"),
    ("cyberghost", "CyberGhost"),
    ("expressvpn", "ExpressVPN"),

    ("adobe", "Adobe"),
    ("photoshop", "Adobe"),
    ("acrobat", "Adobe"),
    ("autodesk", "Autodesk"),
    ("autocad", "Autodesk"),
    ("coreldraw", "Corel"),

    ("youtube premium", "Google"),
    ("google one", "Google"),

    ("ea sports fc", "Electronic Arts"),
    ("fifa", "Electronic Arts"),
    ("resident evil", "Capcom"),
    ("nioh", "Koei Tecmo"),
    ("crimson desert", "Pearl Abyss"),
    ("arc raiders", "Embark Studios"),
    ("007: first light", "IO Interactive"),
]


# Custom Trovaprezzi categories
CATEGORY_RULES = {
    "XBOX-GPE1": "Abbonamenti Gaming",
    "XBOX-GPU3": "Abbonamenti Gaming",
    "XBOX-GPU1": "Abbonamenti Gaming",
    "XBOX-GPE3": "Abbonamenti Gaming",
}


QUERY = """
query GetProducts($cursor: String) {

  products(
    first: 100
    after: $cursor
    query: "status:ACTIVE"
  ) {

    pageInfo {
      hasNextPage
      endCursor
    }

    nodes {

      title
      handle
      vendor
      descriptionHtml

      category {
        name
        fullName
      }

      italianTranslations: translations(locale: "it") {
        key
        value
      }

      frenchTranslations: translations(locale: "fr") {
        key
        value
      }

      images(first: 10) {
        nodes {
          url
        }
      }

      variants(first: 1) {
        nodes {
          sku
          price

          inventoryItem {
            tracked

            inventoryLevels(first: 1) {
              nodes {
                quantities(names: ["available"]) {
                  name
                  quantity
                }
              }
            }
          }

          image {
            url
          }
        }
      }
    }
  }
}
"""



def normalize_product_name(name):
    if not name:
        return ""
    name = html.unescape(str(name))
    name = re.sub(r"\s+", " ", name)
    return name.strip().casefold()


def clean_gtin(gtin):
    if gtin is None:
        return ""
    gtin = str(gtin).strip()
    if not gtin:
        return ""
    if re.fullmatch(r"\d+\.0", gtin):
        gtin = gtin[:-2]
    return re.sub(r"\D", "", gtin)


def get_gtin_map():
    response = requests.get(GOOGLE_SHEET_CSV_URL, timeout=30)
    response.raise_for_status()
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    if not rows:
        raise Exception("Google Spreadsheet is empty.")
    headers = [str(x).strip().casefold() for x in rows[0]]
    try:
        product_index = headers.index("product")
        gtin_index = headers.index("gtin")
    except ValueError:
        raise Exception("Spreadsheet first row must contain Product and GTIN headers.")
    result = {}
    for row in rows[1:]:
        if len(row) <= max(product_index, gtin_index):
            continue
        product = row[product_index].strip()
        gtin = clean_gtin(row[gtin_index])
        if product and gtin:
            result[normalize_product_name(product)] = gtin
    return result


def get_translations(product, language):

    translations = {}

    if language == "it":
        translation_list = product.get(
            "italianTranslations",
            []
        )

    elif language == "fr":
        translation_list = product.get(
            "frenchTranslations",
            []
        )

    else:
        translation_list = []

    for translation in translation_list:

        key = translation.get("key")
        value = translation.get("value")

        if key and value:
            translations[key] = value

    return translations


def detect_brand(title, vendor):

    title_lower = title.lower()

    for keyword, brand in BRAND_RULES:

        if keyword in title_lower:
            return brand

    if vendor and vendor.strip():
        return vendor.strip()

    return "SAIVERA"


def clean_description(description):

    if not description:
        return ""

    description = html.unescape(description)

    description = re.sub(
        r"<[^>]+>",
        " ",
        description
    )

    description = re.sub(
        r"\s+",
        " ",
        description
    )

    return description.strip()


def get_category(product):

    category = product.get("category")

    if not category:
        return "Computer Software"

    full_name = category.get("fullName")
    name = category.get("name")

    # Custom category:
    # Software > Video Game Software > Digital Video Games
    # becomes:
    # Video Games
    if full_name == "Software > Video Game Software > Digital Video Games":
        return "Video Games"

    if full_name:

        if " in " in full_name:

            parts = full_name.split(" in ")
            parts.reverse()

            return " > ".join(
                part.strip()
                for part in parts
            )

        return full_name

    return name or "Computer Software"


def get_category_for_variant(product, sku):

    # Every SKU beginning with XBOX-
    # gets the custom Trovaprezzi category
    if sku and sku.strip().upper().startswith("XBOX-"):
        return "Abbonamenti Gaming"

    return get_category(product)


def get_stock_status(variant):

    inventory_item = variant.get("inventoryItem")

    if not inventory_item:
        return "disponibile"

    tracked = inventory_item.get("tracked")

    # Inventory tracking disabled
    if not tracked:
        return "disponibile"

    inventory_levels = (
        inventory_item
        .get("inventoryLevels", {})
        .get("nodes", [])
    )

    total_available = 0
    found_quantity = False

    for level in inventory_levels:

        quantities = level.get(
            "quantities",
            []
        )

        for quantity_data in quantities:

            if quantity_data.get("name") == "available":

                quantity = quantity_data.get(
                    "quantity",
                    0
                )

                total_available += quantity
                found_quantity = True

    if found_quantity and total_available > 0:
        return "disponibile"

    return "non disponibile"


def get_products():

    products = []

    cursor = None

    while True:

        response = requests.post(
            URL,
            headers=HEADERS,
            json={
                "query": QUERY,
                "variables": {
                    "cursor": cursor
                }
            }
        )

        response.raise_for_status()

        data = response.json()

        if "errors" in data:
            raise Exception(data["errors"])

        product_data = data["data"]["products"]

        products.extend(
            product_data["nodes"]
        )

        page_info = product_data["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]

    return products


def add_field(parent, name, value):

    element = ET.SubElement(
        parent,
        name
    )

    element.text = str(
        value or ""
    )

    return element


def generate_offer(
    root,
    product,
    variant,
    title,
    description,
    product_url,
    brand,
    gtin
):

    offer = ET.SubElement(
        root,
        "Offer"
    )

    sku = variant.get("sku", "")

    price = variant.get(
        "price",
        "0"
    )

    images = (
        product
        .get("images", {})
        .get("nodes", [])
    )

    default_image = ""

    if images:

        default_image = (
            images[0]
            .get("url", "")
        )

    image = default_image

    variant_image = variant.get(
        "image"
    )

    if variant_image:

        image = variant_image.get(
            "url",
            ""
        )

    category = get_category_for_variant(
        product,
        sku
    )

    stock_status = get_stock_status(
        variant
    )

    add_field(
        offer,
        "Name",
        title
    )

    add_field(
        offer,
        "Brand",
        brand
    )

    add_field(
        offer,
        "Description",
        description
    )

    add_field(
        offer,
        "Price",
        price
    )

    add_field(
        offer,
        "Code",
        gtin
    )

    add_field(
        offer,
        "Link",
        product_url
    )

    add_field(
        offer,
        "Stock",
        stock_status
    )

    add_field(
        offer,
        "Categories",
        category
    )

    add_field(
        offer,
        "Image",
        image
    )

    add_field(
        offer,
        "ShippingCost",
        "0"
    )


def save_xml(root, filename):

    xml_string = ET.tostring(
        root,
        encoding="utf-8"
    )

    pretty_xml = (
        minidom
        .parseString(
            xml_string
        )
        .toprettyxml(
            indent="  ",
            encoding="UTF-8"
        )
    )

    with open(
        filename,
        "wb"
    ) as file:

        file.write(
            pretty_xml
        )


def generate_feed():

    gtin_map = get_gtin_map()

    products = get_products()

    italian_root = ET.Element(
        "Products"
    )

    english_root = ET.Element(
        "Products"
    )

    french_root = ET.Element(
        "Products"
    )

    total_offers = 0

    available_offers = 0
    unavailable_offers = 0

    products_with_gtin = []

    for product in products:
        gtin = gtin_map.get(normalize_product_name(product.get("title", "")), "")
        if not gtin:
            continue
        product["_feed_gtin"] = gtin
        products_with_gtin.append(product)

    for product in products_with_gtin:

        gtin = product["_feed_gtin"]

        # Italian translations
        italian_translations = get_translations(
            product,
            "it"
        )

        # French translations
        french_translations = get_translations(
            product,
            "fr"
        )

        # Original English content
        original_title = product.get(
            "title",
            ""
        )

        original_description = product.get(
            "descriptionHtml",
            ""
        )

        # Italian
        italian_title = italian_translations.get(
            "title",
            original_title
        )

        italian_description_html = italian_translations.get(
            "body_html",
            original_description
        )

        italian_description = clean_description(
            italian_description_html
        )

        # English
        english_title = original_title

        english_description = clean_description(
            original_description
        )

        # French
        french_title = french_translations.get(
            "title",
            original_title
        )

        french_description_html = french_translations.get(
            "body_html",
            original_description
        )

        french_description = clean_description(
            french_description_html
        )

        handle = product.get(
            "handle",
            ""
        )

        vendor = product.get(
            "vendor",
            ""
        )

        brand = detect_brand(
            original_title,
            vendor
        )

        # Italian URL
        italian_url = (
            "https://saivera.net/it/products/"
            + handle
        )

        # English URL
        english_url = (
            "https://saivera.net/products/"
            + handle
        )

        # French URL
        french_url = (
            "https://saivera.net/fr/products/"
            + handle
        )

        variants = (
            product
            .get("variants", {})
            .get("nodes", [])
        )

        for variant in variants:

            stock_status = get_stock_status(
                variant
            )

            if stock_status == "disponibile":
                available_offers += 1
            else:
                unavailable_offers += 1

            # Italian offer
            generate_offer(
                italian_root,
                product,
                variant,
                italian_title,
                italian_description,
                italian_url,
                brand,
                gtin
            )

            # English offer
            generate_offer(
                english_root,
                product,
                variant,
                english_title,
                english_description,
                english_url,
                brand,
                gtin
            )

            # French offer
            generate_offer(
                french_root,
                product,
                variant,
                french_title,
                french_description,
                french_url,
                brand,
                gtin
            )

            total_offers += 1

    # Save Italian feed
    save_xml(
        italian_root,
        "feed-it.xml"
    )

    # Save English feed
    save_xml(
        english_root,
        "feed-en.xml"
    )

    save_xml(
        english_root,
        "product-en.xml"
    )

    # Save French feed
    save_xml(
        french_root,
        "feed-fr.xml"
    )

    print(
        "Feeds generated successfully."
    )

    print(
        f"Active products: {len(products)}"
    )

    print(
        f"Offers per feed: {total_offers}"
    )

    print(
        f"Available offers: {available_offers}"
    )

    print(
        f"Unavailable offers: {unavailable_offers}"
    )

    print(
        "Italian feed: feed-it.xml"
    )

    print(
        "English feed: feed-en.xml"
    )

    print(
        "French feed: feed-fr.xml"
    )


if __name__ == "__main__":

    generate_feed()
  
