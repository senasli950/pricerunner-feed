import os
import re
import html
import csv
import io
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom


# =========================================================
# SHOPIFY
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
    "Content-Type": "application/json"
}


# =========================================================
# GOOGLE SHEETS
# =========================================================

GOOGLE_SHEET_ID = (
    "14xegQdHjQBytqo-k2E6N8H3AeCqRqvEJ3BmSTZgTQRY"
)

GOOGLE_SHEET_NAME = "GTIN"


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
# CUSTOM TROVAPREZZI CATEGORIES
# =========================================================

CATEGORY_RULES = {
    "XBOX-GPE1": "Abbonamenti Gaming",
    "XBOX-GPU3": "Abbonamenti Gaming",
    "XBOX-GPU1": "Abbonamenti Gaming",
    "XBOX-GPE3": "Abbonamenti Gaming",
}


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

      translations(locale: "it") {
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

          inventoryItem {
            tracked

            inventoryLevels(first: 10) {
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


# =========================================================
# GET GOOGLE SHEETS GTIN DATA
# =========================================================

def get_gtin_map():

    print("Downloading GTIN spreadsheet...")

    # -----------------------------------------------------
    # Use Google Sheets export CSV directly.
    #
    # This avoids the GViz header issue.
    # -----------------------------------------------------

    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{GOOGLE_SHEET_ID}/export"
    )

    params = {
        "format": "csv",
        "sheet": GOOGLE_SHEET_NAME
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    csv_text = response.text

    print(
        f"GTIN CSV downloaded: "
        f"{len(csv_text)} characters"
    )

    reader = csv.reader(
        io.StringIO(csv_text)
    )

    rows = list(reader)

    if not rows:

        raise Exception(
            "GTIN spreadsheet returned no rows."
        )

    # -----------------------------------------------------
    # Find Product / GTIN header
    # -----------------------------------------------------

    header_row_index = None
    product_index = None
    gtin_index = None

    for index, row in enumerate(rows):

        normalized = [
            str(value)
            .strip()
            .lower()
            for value in row
        ]

        if "product" in normalized and "gtin" in normalized:

            header_row_index = index

            product_index = normalized.index(
                "product"
            )

            gtin_index = normalized.index(
                "gtin"
            )

            break

    if header_row_index is None:

        print("First spreadsheet rows:")

        for row in rows[:5]:
            print(row)

        raise Exception(
            "Could not find Product and GTIN headers."
        )

    print(
        f"GTIN header found on spreadsheet row "
        f"{header_row_index + 1}"
    )

    print(
        f"Product column: {product_index + 1}"
    )

    print(
        f"GTIN column: {gtin_index + 1}"
    )

    # -----------------------------------------------------
    # Build map
    # -----------------------------------------------------

    gtin_map = {}

    for row in rows[header_row_index + 1:]:

        if len(row) <= max(
            product_index,
            gtin_index
        ):
            continue

        product = str(
            row[product_index]
        ).strip()

        gtin = str(
            row[gtin_index]
        ).strip()

        # Ignore empty product
        if not product:
            continue

        # IMPORTANT:
        # Ignore products without GTIN
        if not gtin:
            continue

        # Normalize product name
        product_key = re.sub(
            r"\s+",
            " ",
            product
        ).strip().lower()

        gtin_map[product_key] = gtin

    print(
        f"GTIN products loaded: {len(gtin_map)}"
    )

    return gtin_map


# =========================================================
# TRANSLATIONS
# =========================================================

def get_translations(product):

    translations = {}

    for translation in product.get(
        "translations",
        []
    ):

        key = translation.get("key")
        value = translation.get("value")

        if key and value:

            translations[key] = value

    return translations


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

    description = html.unescape(
        description
    )

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


# =========================================================
# CATEGORY
# =========================================================

def get_category(product):

    category = product.get(
        "category"
    )

    if not category:

        return "Computer Software"

    full_name = category.get(
        "fullName"
    )

    name = category.get(
        "name"
    )

    # -----------------------------------------------------
    # Digital Video Games
    #
    # Software > Video Game Software >
    # Digital Video Games
    #
    # becomes:
    #
    # Video Games
    # -----------------------------------------------------

    if full_name == (
        "Software > Video Game Software > "
        "Digital Video Games"
    ):

        return "Video Games"

    if full_name:

        if " in " in full_name:

            parts = full_name.split(
                " in "
            )

            parts.reverse()

            return " > ".join(
                part.strip()
                for part in parts
            )

        return full_name

    return (
        name
        or
        "Computer Software"
    )


def get_category_for_variant(
    product,
    sku
):

    if sku:

        sku_clean = sku.strip().upper()

        if sku_clean.startswith(
            "XBOX-"
        ):

            return "Abbonamenti Gaming"

    return get_category(
        product
    )


# =========================================================
# STOCK
# =========================================================

def get_stock_status(variant):

    inventory_item = variant.get(
        "inventoryItem"
    )

    # Safety fallback
    if not inventory_item:

        return "disponibile"

    tracked = inventory_item.get(
        "tracked"
    )

    # If Shopify does not track inventory,
    # treat it as available.
    if not tracked:

        return "disponibile"

    inventory_levels = (
        inventory_item
        .get(
            "inventoryLevels",
            {}
        )
        .get(
            "nodes",
            []
        )
    )

    total_available = 0

    found_quantity = False

    for level in inventory_levels:

        quantities = level.get(
            "quantities",
            []
        )

        for quantity_data in quantities:

            if (
                quantity_data.get("name")
                == "available"
            ):

                quantity = quantity_data.get(
                    "quantity",
                    0
                )

                total_available += quantity

                found_quantity = True

    if (
        found_quantity
        and
        total_available > 0
    ):

        return "disponibile"

    return "non disponibile"


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
                    "cursor": cursor
                }
            },
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        if "errors" in data:

            raise Exception(
                data["errors"]
            )

        product_data = (
            data["data"]["products"]
        )

        products.extend(
            product_data["nodes"]
        )

        page_info = (
            product_data["pageInfo"]
        )

        if not page_info[
            "hasNextPage"
        ]:

            break

        cursor = (
            page_info["endCursor"]
        )

    print(
        f"Active Shopify products: "
        f"{len(products)}"
    )

    return products


# =========================================================
# ADD XML FIELD
# =========================================================

def add_field(
    parent,
    name,
    value
):

    element = ET.SubElement(
        parent,
        name
    )

    element.text = str(
        value
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
    brand
):

    offer = ET.SubElement(
        root,
        "Offer"
    )

    price = variant.get(
        "price",
        "0"
    )

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

    # -----------------------------------------------------
    # Category
    # -----------------------------------------------------

    sku = variant.get(
        "sku"
    )

    category = get_category_for_variant(
        product,
        sku
    )

    # -----------------------------------------------------
    # Stock
    # -----------------------------------------------------

    stock_status = get_stock_status(
        variant
    )

    # -----------------------------------------------------
    # XML
    # -----------------------------------------------------

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

    # IMPORTANT:
    # GTIN instead of SKU
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


# =========================================================
# SAVE XML
# =========================================================

def save_xml(
    root,
    filename
):

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


# =========================================================
# GENERATE FEEDS
# =========================================================

def generate_feed():

    # -----------------------------------------------------
    # Load GTIN map first
    # -----------------------------------------------------

    gtin_map = get_gtin_map()

    # -----------------------------------------------------
    # Load Shopify
    # -----------------------------------------------------

    products = get_products()

    # -----------------------------------------------------
    # XML roots
    # -----------------------------------------------------

    english_root = ET.Element(
        "Products"
    )

    italian_root = ET.Element(
        "Products"
    )

    french_root = ET.Element(
        "Products"
    )

    # -----------------------------------------------------
    # Counters
    # -----------------------------------------------------

    matched_products = 0
    skipped_products = 0

    available_offers = 0
    unavailable_offers = 0

    # -----------------------------------------------------
    # Products
    # -----------------------------------------------------

    for product in products:

        translations = get_translations(
            product
        )

        # -------------------------------------------------
        # Original English
        # -------------------------------------------------

        original_title = product.get(
            "title",
            ""
        )

        original_description = product.get(
            "descriptionHtml",
            ""
        )

        english_title = original_title

        english_description = clean_description(
            original_description
        )

        # -------------------------------------------------
        # Italian
        # -------------------------------------------------

        italian_title = translations.get(
            "title",
            original_title
        )

        italian_description_html = translations.get(
            "body_html",
            original_description
        )

        italian_description = clean_description(
            italian_description_html
        )

        # -------------------------------------------------
        # French
        #
        # Shopify translations need to be requested
        # separately, therefore we retrieve them below
        # using product handle/title if available.
        #
        # To keep the current query lightweight,
        # French is obtained from the product's French
        # translations through a second request.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Product URLs
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Variants
        #
        # You said each product has only one variant.
        # We therefore only use the first one.
        # -------------------------------------------------

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

        # We match using the Shopify product title.
        product_key = re.sub(
            r"\s+",
            " ",
            original_title
        ).strip().lower()

        gtin = gtin_map.get(
            product_key
        )

        # -------------------------------------------------
        # No GTIN = do not put product
        # in any feed.
        # -------------------------------------------------

        if not gtin:

            skipped_products += 1

            continue

        matched_products += 1

        # -------------------------------------------------
        # Stock statistics
        # -------------------------------------------------

        stock_status = get_stock_status(
            variant
        )

        if stock_status == "disponibile":

            available_offers += 1

        else:

            unavailable_offers += 1

        # ---------------------------
