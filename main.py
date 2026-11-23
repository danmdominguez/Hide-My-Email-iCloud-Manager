import argparse
import json
import time
from datetime import datetime
from typing import Dict, List
import requests
from rich.console import Console

console = Console()

# Markdown columns, left to right. Records are grouped by forwarding
# address, then active and inactive, newest first inside each table.
OUTPUT_FIELDS = [
    "label",
    "hme",
    "note",
    "createTimestamp",
    "isActive",
    "anonymousId",
]


# -------------------------------------------------------
# LOAD COOKIES
# -------------------------------------------------------

def load_cookies() -> Dict[str, str]:
    """
    Loads cookies from cookies.txt where the user pastes a Python dict like:
    cookies = {
        "name": "value",
        ...
    }
    """
    try:
        with open("cookies.txt", "r", encoding="utf-8") as f:
            content = f.read()

        # Local dictionary to capture executed variables
        local_vars = {}
        exec(content, {}, local_vars)

        if "cookies" not in local_vars:
            console.print("[bold red]cookies.txt is missing the variable 'cookies'[/]")
            return {}

        return local_vars["cookies"]

    except FileNotFoundError:
        console.print("[bold red]cookies.txt not found![/]")
        return {}
    except Exception as e:
        console.print(f"[bold red]Error reading cookies.txt: {e}[/]")
        return {}



# -------------------------------------------------------
# GLOBAL HEADERS
# -------------------------------------------------------

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "text/plain",
    "Origin": "https://www.icloud.com",
    "Referer": "https://www.icloud.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Chromium";"Google Chrome";"Not A(Brand"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


# -------------------------------------------------------
# UTIL: CLEAN API RESPONSE
# -------------------------------------------------------

def parse_response(res):
    """
    Converts Apple API response into readable status messages.
    """
    try:
        data = res.json()

        if data.get("success"):
            return True, "Success"

        if "error" in data:
            err = data["error"]
            reason = err.get("errorMessage", "Unknown error")
            return False, reason

        return False, "Unknown response format"

    except Exception:
        return False, "Invalid JSON response"


# -------------------------------------------------------
# FETCH HME LIST
# -------------------------------------------------------

def fetch_hme_list(cookies: Dict[str, str]) -> List[Dict]:
    dsid = cookies["X-APPLE-WEBAUTH-USER"].split("d=")[-1].replace('"', "")

    params = {
        "clientBuildNumber": "2542Build17",
        "clientMasteringNumber": "2542Build17",
        "clientId": "auto-script",
        "dsid": dsid
    }

    url = "https://p158-maildomainws.icloud.com/v2/hme/list"

    console.print("[bold cyan]Fetching Hide My Email list...[/]")

    res = requests.get(url, headers=HEADERS, cookies=cookies, params=params)

    try:
        return res.json()["result"]["hmeEmails"]
    except:
        console.print("[bold red]❌ Failed to parse response from Apple[/]")
        console.print(res.text)
        return []


# -------------------------------------------------------
# DEACTIVATE
# -------------------------------------------------------

def deactivate_hme(cookies: Dict[str, str], anon_id: str):
    dsid = cookies["X-APPLE-WEBAUTH-USER"].split("d=")[-1].replace('"', "")
    url = "https://p158-maildomainws.icloud.com/v1/hme/deactivate"
    payload = json.dumps({"anonymousId": anon_id})

    params = {
        "clientBuildNumber": "2542Build17",
        "clientMasteringNumber": "2542Build17",
        "clientId": "auto-script",
        "dsid": dsid
    }

    res = requests.post(url, headers=HEADERS, cookies=cookies, params=params, data=payload)
    return parse_response(res)


# -------------------------------------------------------
# DELETE
# -------------------------------------------------------

def delete_hme(cookies: Dict[str, str], anon_id: str):
    dsid = cookies["X-APPLE-WEBAUTH-USER"].split("d=")[-1].replace('"', "")
    url = "https://p158-maildomainws.icloud.com/v1/hme/delete"
    payload = json.dumps({"anonymousId": anon_id})

    params = {
        "clientBuildNumber": "2542Build17",
        "clientMasteringNumber": "2542Build17",
        "clientId": "auto-script",
        "dsid": dsid
    }

    res = requests.post(url, headers=HEADERS, cookies=cookies, params=params, data=payload)
    return parse_response(res)


# -------------------------------------------------------
# EXPORT
# -------------------------------------------------------

def format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def format_timestamp(value) -> str:
    if value in (None, ""):
        return ""
    moment = datetime.fromtimestamp(int(value) / 1000)
    return moment.strftime("%Y.%m.%d %H%M")


def display_value(column: str, value) -> str:
    if column == "createTimestamp":
        return format_timestamp(value)
    return format_cell(value)


def markdown_cell(column: str, value) -> str:
    text = display_value(column, value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    return text


def record_timestamp(record: Dict) -> int:
    value = record.get("createTimestamp") or 0
    return int(value)


def render_table(records: List[Dict], columns: List[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for record in records:
        cells = [markdown_cell(column, record.get(column)) for column in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown(hme_list: List[Dict], columns: List[str]) -> str:
    grouped: Dict[str, List[Dict]] = {}
    for record in hme_list:
        address = record.get("forwardToEmail") or ""
        grouped.setdefault(address, []).append(record)

    def group_order(address: str):
        newest = max(record_timestamp(record) for record in grouped[address])
        return (-newest, address.lower())

    parts = []
    for address in sorted(grouped, key=group_order):
        records = grouped[address]
        parts.append(f"## {address or '(no forwarding address)'}")
        parts.append("")
        sections = (
            ("Active", [record for record in records if record.get("isActive")]),
            ("Inactive", [record for record in records if not record.get("isActive")]),
        )
        for label, section in sections:
            section.sort(key=record_timestamp, reverse=True)
            parts.append(f"### {label}")
            parts.append("")
            parts.append(render_table(section, columns))
            parts.append("")
    return "\n".join(parts)


def save_export(hme_list: List[Dict]) -> List[str]:
    """Write one Active and Inactive table under each forwarding address."""
    columns = list(OUTPUT_FIELDS)
    with open("emails.md", "w", encoding="utf-8") as f:
        f.write(render_markdown(hme_list, columns))
    return columns


# -------------------------------------------------------
# CLI
# -------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage Apple iCloud Hide My Email addresses from the command line."
    )
    parser.add_argument(
        "--export-only",
        "--list-only",
        "--toggle",
        action="store_true",
        dest="export_only",
        help="List and export emails without deactivating or deleting them",
    )
    return parser.parse_args()


# -------------------------------------------------------
# MAIN SCRIPT
# -------------------------------------------------------

def main(export_only: bool = False):

    console.print("[bold green]🚀 Hide My Email Manager[/]")

    cookies = load_cookies()

    if not cookies:
        console.print("[red]No cookies loaded![/]")
        return

    hme_list = fetch_hme_list(cookies)

    if not hme_list:
        console.print("[yellow]No Hide My Email entries found.[/]")
        return

    columns = save_export(hme_list)
    console.print(
        f"[green]Saved {len(hme_list)} entries "
        f"({len(columns)} fields) to emails.md[/]\n"
    )
    console.print(render_markdown(hme_list, columns))

    if export_only:
        console.print(
            "\n[bold green]Export-only mode — skipping deactivation and deletion.[/]"
        )
        return

    console.print("\n[bold red]Starting deactivation + deletion...[/]")

    for h in hme_list:

        anon = h["anonymousId"]
        email = h["hme"]

        console.print("\n[cyan]────────────────────────────────────────[/]")
        console.print(f"[white]📧 Email:[/] {email}")
        console.print(f"[white]🔑 ID:[/] {anon}")

        # Status
        if h["isActive"]:
            console.print("[yellow]🟡 Status: ACTIVE[/]")

            ok, msg = deactivate_hme(cookies, anon)
            icon = "✔" if ok else "✖"
            console.print(f" → Deactivating... {icon} {msg}")
            time.sleep(1)

        else:
            console.print("[blue]🔵 Status: INACTIVE (skipping deactivation)[/]")

        # Delete
        ok, msg = delete_hme(cookies, anon)
        icon = "✔" if ok else "✖"
        console.print(f" → Deleting....... {icon} {msg}")
        time.sleep(1)

        console.print("[cyan]────────────────────────────────────────[/]")

    console.print("\n[bold green]✔ All entries processed successfully![/]")


if __name__ == "__main__":
    args = parse_args()
    main(export_only=args.export_only)
