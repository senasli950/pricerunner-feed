import os
import re
import html
import csv
import io
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom



# =========================================================
#def find_gtin(product_title, gtin_map): SHOPIFY
# =========================================================

SHOPIFY_STORE = "it3u3i-5e.myshopify.com"
ACCESS_TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
API_VERSION = "2025-01"

URL = (
    f"https://{SHOPIFY_STORE}"
    f"/admin/api/{API_VERSION}/graphql.json"
)

HEADERS = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json",
}


# =========================================================
# GOOGLE SHEETS
# =========================================================

GOOGLE_SHEET_ID = "14xegQdHjQBytqo-k2E6N8H3AeCqRqvEJ3BmSTZgTQRY"
GOOGLE_SHEET_GID = "642575637"


# =========================================================
# BRAND RULES
# =========================================================

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


# =========================================================
# SHOPIFY QUERY
# =========================================================

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

      images(first: 1) {
        nodes {
          url
        }
      }

      variants(first: 1) {
        nodes {
          sku
          price
          availableForSale

          image {
            url
          }
        }
      }
    }
  }
}
"""


# =========================================================
# NORMALIZE PRODUCT NAME
# =========================================================

def normalize_product_name(value):
    """
    Normalizes names only for matching.
    It does NOT change the title written into the XML.
    """

    if value is None:
        return ""

    value = html.unescape(str(value))
    value = value.replace("\u00a0", " ")

    # Normalize common dash variants.
    value = value.replace("–", "-")
    value = value.replace("—", "-")
    value = value.replace("−", "-")

    # Normalize quotes.
    value = value.replace("’", "'")
    value = value.replace("‘", "'")
    value = value.replace("“", '"')
    value = value.replace("”", '"')

    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)

    return value


def clean_gtin(value):
    """
    Keep GTIN as text so leading zeroes are preserved.
    Accept standard GTIN lengths 8-14 digits.
    """

    if value is None:
        return ""

    value = str(value).strip()

    # Remove spaces sometimes introduced by spreadsheet cells.
    value = re.sub(r"\s+", "", value)

    if not value.isdigit():
        return ""

    if not 8 <= len(value) <= 14:
        return ""

    return value


# =========================================================
# GET GOOGLE SHEETS GTIN DATA
# =========================================================

def get_gtin_map():

    print("Downloading GTIN spreadsheet...")

    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{GOOGLE_SHEET_ID}/export"
    )

    params = {
    "format": "csv",
    "gid": GOOGLE_SHEET_GID,
}

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    csv_text = response.text

    print(f"GTIN CSV downloaded: {len(csv_text)} characters")

    rows = list(csv.reader(io.StringIO(csv_text)))

    if not rows:
        raise Exception("GTIN spreadsheet returned no rows.")

    print("First spreadsheet rows:")
    for row in rows[:5]:
        print(row)

    # -----------------------------------------------------
    # IMPORTANT FIX
    #
    # Do NOT depend on the Product / GTIN header.
    #
    # The Google export used by the sheet can return the
    # first row with the header attached to the first
    # product, e.g.:
    #
    # ['Product Xbox Game Pass ...', 'GTIN ']
    #
    # Therefore we simply detect rows where column B is
    # actually a valid GTIN.
    # -----------------------------------------------------

    gtin_map = {}

    for row in rows:

        if len(row) < 2:
            continue

        product = str(row[0]).strip()
        gtin = clean_gtin(row[1])

        # Only real GTIN rows are accepted.
        if not product or not gtin:
            continue

        product_key = normalize_product_name(product)

        if not product_key:
            continue

        gtin_map[product_key] = gtin

    print(f"GTIN products loaded: {len(gtin_map)}")

    if not gtin_map:
        raise Exception(
            "No valid GTIN rows were found. "
            "Check that GTIN values are in column B of the GTIN sheet."
        )

    return gtin_map


# =========================================================
# GTIN MATCHING
# =========================================================


def find_gtin(product_title, gtin_map):
    key = normalize_product_name(product_title)

    gtin = gtin_map.get(key)

    if gtin:
        return gtin, "exact"

    return None, None


# =========================================================
# TRANSLATIONS
# =========================================================

def get_translation_map(translations):

    result = {}

    for translation in translations or []:

        key = translation.get("key")
        value = translation.get("value")

        if key and value:
            result[key] = value

    return result


# =========================================================
# BRAND
# =========================================================

def detect_brand(title, vendor):

    title_lower = title.lower()

    for keyword, brand in BRAND_RULES:

        if keyword in title_lower:
            return brand

    if vendor and vendor.strip():
        return vendor.strip()

    return "SAIVERA"


# =========================================================
# CLEAN DESCRIPTION
# =========================================================

def clean_description(description):

    if not description:
        return ""

    description = html.unescape(description)

    description = re.sub(
        r"<[^>]+>",
        " ",
        description,
    )

    description = re.sub(
        r"\s+",
        " ",
        description,
    )

    return description.strip()


# =========================================================
# CATEGORY
# =========================================================

def get_category(product):

    category = product.get("category")

    if not category:
        return "Computer Software"

    full_name = category.get("fullName")
    name = category.get("name")

    if full_name == (
        "Software > Video Game Software > "
        "Digital Video Games"
    ):
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

    if sku:

        sku_clean = sku.strip().upper()

        if sku_clean.startswith("XBOX-"):
            return "Abbonamenti Gaming"

    return get_category(product)


# =========================================================
# STOCK
# =========================================================

def get_stock_status(variant):

    # availableForSale is enough for the feed's
    # available/unavailable status and avoids expensive
    # inventoryLevels queries.
    if variant.get("availableForSale") is False:
        return "non disponibile"

    return "disponibile"


# =========================================================
# GET SHOPIFY PRODUCTS
# =========================================================

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
                    "cursor": cursor,
                },
            },
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        if "errors" in data:
            raise Exception(data["errors"])

        if not data.get("data") or not data["data"].get("products"):
            raise Exception(
                f"Unexpected Shopify response: {data}"
            )

        product_data = data["data"]["products"]

        products.extend(product_data["nodes"])

        page_info = product_data["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]

    print(f"Active Shopify products: {len(products)}")

    return products


# =========================================================
# ADD XML FIELD
# =========================================================

def add_field(parent, name, value):

    element = ET.SubElement(
        parent,
        name,
    )

    element.text = (
        str(value)
        if value is not None
        else ""
    )

    return element


# =========================================================
# GENERATE OFFER
# =========================================================

def generate_offer(
    root,
    product,
    variant,
    gtin,
    title,
    description,
    product_url,
    brand,
):

    offer = ET.SubElement(
        root,
        "Offer",
    )

    price = variant.get("price", "0")

    # -----------------------------------------------------
    # Image
    # -----------------------------------------------------

    images = (
        product
        .get("images", {})
        .get("nodes", [])
    )

    default_image = ""

    if images:
        default_image = images[0].get("url", "")

    image = default_image

    variant_image = variant.get("image")

    if variant_image:
        image = variant_image.get("url", "")

    # -----------------------------------------------------
    # Category
    # -----------------------------------------------------

    sku = variant.get("sku")

    category = get_category_for_variant(
        product,
        sku,
    )

    # -----------------------------------------------------
    # Stock
    # -----------------------------------------------------

    stock_status = get_stock_status(variant)

    # -----------------------------------------------------
    # XML
    # -----------------------------------------------------

    add_field(
        offer,
        "Name",
        title,
    )

    add_field(
        offer,
        "Brand",
        brand,
    )

    add_field(
        offer,
        "Description",
        description,
    )

    add_field(
        offer,
        "Price",
        price,
    )

    # GTIN instead of SKU.
    add_field(
        offer,
        "Code",
        gtin,
    )

    add_field(
        offer,
        "Link",
        product_url,
    )

    add_field(
        offer,
        "Stock",
        stock_status,
    )

    add_field(
        offer,
        "Categories",
        category,
    )

    add_field(
        offer,
        "Image",
        image,
    )

    add_field(
        offer,
        "ShippingCost",
        "0",
    )


# =========================================================
# SAVE XML
# =========================================================

def save_xml(root, filename):

    xml_string = ET.tostring(
        root,
        encoding="utf-8",
    )

    pretty_xml = (
        minidom
        .parseString(xml_string)
        .toprettyxml(
            indent="  ",
            encoding="UTF-8",
        )
    )

    with open(
        filename,
        "wb",
    ) as file:
        file.write(pretty_xml)


# =========================================================
# GENERATE FEEDS
# =========================================================

def generate_feed():

    gtin_map = get_gtin_map()

    products = get_products()

    english_root = ET.Element("Products")
    italian_root = ET.Element("Products")
    french_root = ET.Element("Products")

    matched_products = 0
    skipped_products = 0

    exact_matches = 0
    fuzzy_matches = 0

    available_offers = 0
    unavailable_offers = 0

    for product in products:

        original_title = product.get("title", "")
        original_description = product.get(
            "descriptionHtml",
            "",
        )

        english_title = original_title

        english_description = clean_description(
            original_description
        )

        # -------------------------------------------------
        # Italian
        # -------------------------------------------------

        italian_translations = get_translation_map(
            product.get("italianTranslations", [])
        )

        italian_title = italian_translations.get(
            "title",
            original_title,
        )

        italian_description = clean_description(
            italian_translations.get(
                "body_html",
                original_description,
            )
        )

        # -------------------------------------------------
        # French
        # -------------------------------------------------

        french_translations = get_translation_map(
            product.get("frenchTranslations", [])
        )

        french_title = french_translations.get(
            "title",
            original_title,
        )

        french_description = clean_description(
            french_translations.get(
                "body_html",
                original_description,
            )
        )

        handle = product.get("handle", "")
        vendor = product.get("vendor", "")

        brand = detect_brand(
            original_title,
            vendor,
        )

        english_url = (
            "https://saivera.net/products/"
            + handle
        )

        italian_url = (
            "https://saivera.net/it/products/"
            + handle
        )

        french_url = (
            "https://saivera.net/fr/products/"
            + handle
        )

        variants = (
            product
            .get("variants", {})
            .get("nodes", [])
        )

        if not variants:
            skipped_products += 1
            continue

        variant = variants[0]

        # -------------------------------------------------
        # GTIN matching
        # -------------------------------------------------

        gtin, match_type = find_gtin(
            original_title,
            gtin_map,
        )

        if not gtin:

            skipped_products += 1

            print(
                f"NO GTIN: {original_title}"
            )

            continue

        matched_products += 1

        if match_type == "exact":
            exact_matches += 1
        else:
            fuzzy_matches += 1
            print(
                f"GTIN fuzzy match: "
                f"{original_title} -> {gtin} "
                f"({match_type})"
            )

        stock_status = get_stock_status(variant)

        if stock_status == "disponibile":
            available_offers += 1
        else:
            unavailable_offers += 1

        # -------------------------------------------------
        # English
        # -------------------------------------------------

        generate_offer(
            english_root,
            product,
            variant,
            gtin,
            english_title,
            english_description,
            english_url,
            brand,
        )

        # -------------------------------------------------
        # Italian
        # -------------------------------------------------

        generate_offer(
            italian_root,
            product,
            variant,
            gtin,
            italian_title,
            italian_description,
            italian_url,
            brand,
        )

        # -------------------------------------------------
        # French
        # -------------------------------------------------

        generate_offer(
            french_root,
            product,
            variant,
            gtin,
            french_title,
            french_description,
            french_url,
            brand,
        )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    save_xml(english_root, "feed-en.xml")
    save_xml(italian_root, "feed-it.xml")
    save_xml(french_root, "feed-fr.xml")

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    print("")
    print("========================================")
    print("FEED GENERATION COMPLETE")
    print("========================================")
    print(f"GTIN rows loaded:       {len(gtin_map)}")
    print(f"Shopify products:       {len(products)}")
    print(f"Matched products:       {matched_products}")
    print(f"Exact GTIN matches:     {exact_matches}")
    print(f"Fuzzy GTIN matches:     {fuzzy_matches}")
    print(f"Skipped products:       {skipped_products}")
    print(f"Available products:     {available_offers}")
    print(f"Unavailable products:   {unavailable_offers}")
    print("Generated:")
    print("  fees-en.xml")
    print("  fees-it.xml")
    print("  fees-fr.xml")
    print("========================================")


if __name__ == "__main__":
    generate_feed()
        
