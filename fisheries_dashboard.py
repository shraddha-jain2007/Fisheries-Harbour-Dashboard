"""
Building a Relational Fisheries Harbour & Catch Recording Dashboard
------------------------------------------------------------------
One-file application with:
  * SQLite relational database and ON DELETE CASCADE
  * Sample data seeded only when all three tables are empty
  * ipywidgets interface in Jupyter / Google Colab
  * Tkinter interface when run as a normal desktop Python script
  * Command-line fallback when a graphical interface is unavailable

Dependencies:
  - Python 3.9+
  - Jupyter/Colab interface: ipywidgets (usually available in Jupyter;
    in Colab, enable the notebook's ipywidgets support if prompted)
  - Desktop interface: tkinter (included with most standard Python installs)

Run:
  python fisheries_dashboard.py
  or run the whole file in a Jupyter/Colab cell.
"""

import os
import sys
import math
import sqlite3
from contextlib import closing
from datetime import date
from html import escape

# Keep the database next to the script (or in the working folder in a notebook),
# so running from a different directory never creates a second, empty database.
try:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:  # notebook cells have no __file__
    _BASE_DIR = os.getcwd()
DB_FILE = os.path.join(_BASE_DIR, "fisheries_harbour.db")

# Placeholder used when a new harbour is created from the 4-field insert panel.
DEFAULT_HARBOUR_EMAIL = "harbourmaster@fisheries.gov.example"


# ---------------------------------------------------------------------
# DATABASE LAYER
# ---------------------------------------------------------------------

def get_connection():
    """Return a SQLite connection with foreign-key enforcement enabled."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    """Create tables and seed examples only if the database is completely empty."""
    with closing(get_connection()) as conn, conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS harbours (
                harbour_id INTEGER PRIMARY KEY AUTOINCREMENT,
                harbour_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                contact_email TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fishing_trips (
                trip_id INTEGER PRIMARY KEY AUTOINCREMENT,
                harbour_id INTEGER NOT NULL,
                boat_name TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                FOREIGN KEY (harbour_id)
                    REFERENCES harbours(harbour_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS catch_records (
                catch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                catch_type TEXT NOT NULL,
                catch_quantity REAL NOT NULL CHECK (catch_quantity >= 0),
                FOREIGN KEY (trip_id)
                    REFERENCES fishing_trips(trip_id)
                    ON DELETE CASCADE
            );
        """)

        # Seed only when every table is empty; never overwrite existing data.
        counts = [
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("harbours", "fishing_trips", "catch_records")
        ]
        if counts == [0, 0, 0]:
            conn.execute(
                "INSERT INTO harbours (harbour_name, contact_email) VALUES (?, ?)",
                ("Kochi Harbour", "master.kochi@example.com")
            )
            conn.execute(
                "INSERT INTO harbours (harbour_name, contact_email) VALUES (?, ?)",
                ("Mangaluru Harbour", "master.mangalore@example.com")
            )
            conn.execute("""
                INSERT INTO fishing_trips
                    (harbour_id, boat_name, departure_date)
                VALUES
                    ((SELECT harbour_id FROM harbours
                      WHERE harbour_name = 'Kochi Harbour'),
                     'Sea Falcon', '2026-11-06'),
                    ((SELECT harbour_id FROM harbours
                      WHERE harbour_name = 'Mangaluru Harbour'),
                     'Matsya-2', '2026-11-07')
            """)
            conn.execute("""
                INSERT INTO catch_records (trip_id, catch_type, catch_quantity)
                VALUES
                    ((SELECT trip_id FROM fishing_trips
                      WHERE boat_name = 'Sea Falcon'), 'Tuna (kg)', 125.5),
                    ((SELECT trip_id FROM fishing_trips
                      WHERE boat_name = 'Matsya-2'), 'Prawns (kg)', 82)
            """)
            print("Sample fisheries data inserted.")


def fetch_all(query, params=()):
    with closing(get_connection()) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def add_trip_and_catch(harbour_name, boat_name, catch_type, quantity):
    """Reuse an existing harbour or create it, then add one trip and one catch."""
    harbour_name = harbour_name.strip()
    boat_name = boat_name.strip()
    catch_type = catch_type.strip()

    if not all((harbour_name, boat_name, catch_type)):
        raise ValueError("Harbour name, boat name, and catch type cannot be blank.")
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("Catch quantity must be a valid number.")
    if not math.isfinite(quantity):
        raise ValueError("Catch quantity must be a finite number.")
    if quantity < 0:
        raise ValueError("Catch quantity cannot be negative.")

    with closing(get_connection()) as conn, conn:
        harbour = conn.execute(
            "SELECT harbour_id FROM harbours WHERE harbour_name = ?",
            (harbour_name,)
        ).fetchone()

        if harbour:
            harbour_id = harbour["harbour_id"]
        else:
            cur = conn.execute(
                "INSERT INTO harbours (harbour_name, contact_email) VALUES (?, ?)",
                (harbour_name, DEFAULT_HARBOUR_EMAIL)
            )
            harbour_id = cur.lastrowid

        cur = conn.execute("""
            INSERT INTO fishing_trips (harbour_id, boat_name, departure_date)
            VALUES (?, ?, ?)
        """, (harbour_id, boat_name, date.today().isoformat()))
        trip_id = cur.lastrowid

        conn.execute("""
            INSERT INTO catch_records (trip_id, catch_type, catch_quantity)
            VALUES (?, ?, ?)
        """, (trip_id, catch_type, quantity))

    return trip_id


def get_table_data():
    joined = fetch_all("""
        SELECT t.trip_id AS "Trip ID",
               h.harbour_name AS "Harbour Name",
               t.boat_name AS "Boat Name",
               t.departure_date AS "Departure Date",
               c.catch_type AS "Catch Type",
               c.catch_quantity AS "Catch Quantity"
        FROM fishing_trips t
        JOIN harbours h ON h.harbour_id = t.harbour_id
        JOIN catch_records c ON c.trip_id = t.trip_id
        ORDER BY t.trip_id DESC, c.catch_id
    """)
    harbours = fetch_all("""
        SELECT harbour_id AS "Harbour ID",
               harbour_name AS "Harbour Name",
               contact_email AS "Contact Email"
        FROM harbours ORDER BY harbour_id
    """)
    trips = fetch_all("""
        SELECT trip_id AS "Trip ID", harbour_id AS "Harbour ID",
               boat_name AS "Boat Name", departure_date AS "Departure Date"
        FROM fishing_trips ORDER BY trip_id
    """)
    catches = fetch_all("""
        SELECT catch_id AS "Catch ID", trip_id AS "Trip ID",
               catch_type AS "Catch Type", catch_quantity AS "Catch Quantity"
        FROM catch_records ORDER BY catch_id
    """)
    return joined, harbours, trips, catches


def get_delete_options(entity):
    if entity == "Harbour":
        return fetch_all("""
            SELECT harbour_id AS id,
                   harbour_name || ' (ID: ' || harbour_id || ')' AS label
            FROM harbours ORDER BY harbour_name
        """)
    if entity == "Fishing Trip":
        return fetch_all("""
            SELECT trip_id AS id,
                   'Trip ' || trip_id || ' — ' || boat_name AS label
            FROM fishing_trips ORDER BY trip_id
        """)
    return fetch_all("""
        SELECT catch_id AS id,
               'Catch ' || catch_id || ' — ' || catch_type AS label
        FROM catch_records ORDER BY catch_id
    """)


def delete_record(entity, record_id):
    table_and_key = {
        "Harbour": ("harbours", "harbour_id"),
        "Fishing Trip": ("fishing_trips", "trip_id"),
        "Catch Record": ("catch_records", "catch_id"),
    }
    table, key = table_and_key[entity]
    with closing(get_connection()) as conn, conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE {key} = ?", (record_id,))
        if cur.rowcount == 0:
            raise ValueError("That record no longer exists. Refresh and select again.")


# ---------------------------------------------------------------------
# SHARED DISPLAY HELPERS
# ---------------------------------------------------------------------

def format_cell(value):
    """Show floats tidily (1,250.5 instead of 1250.5000); leave everything else alone."""
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def get_cascade_summary(entity, record_id):
    """One-line plain-English description of what a delete will remove."""
    if record_id is None:
        return ""
    with closing(get_connection()) as conn:
        if entity == "Harbour":
            trips = conn.execute(
                "SELECT COUNT(*) FROM fishing_trips WHERE harbour_id = ?", (record_id,)
            ).fetchone()[0]
            catches = conn.execute(
                """SELECT COUNT(*) FROM catch_records c
                   JOIN fishing_trips t ON t.trip_id = c.trip_id
                   WHERE t.harbour_id = ?""", (record_id,)
            ).fetchone()[0]
            return (f"This will also delete {trips} fishing trip(s) and "
                    f"{catches} catch record(s) under this harbour.")
        if entity == "Fishing Trip":
            catches = conn.execute(
                "SELECT COUNT(*) FROM catch_records WHERE trip_id = ?", (record_id,)
            ).fetchone()[0]
            return f"This will also delete {catches} catch record(s) landed on this trip."
    return "Only this catch record is removed. Its trip and harbour stay."


NB_CSS = """
<style>
.fh-banner{background:linear-gradient(135deg,#0b3c5d,#1d6fa5);color:#fff;
  padding:18px 22px;border-radius:12px;font-family:Arial,sans-serif;}
.fh-banner h2{margin:0 0 4px 0;color:#fff;font-size:22px;}
.fh-banner p{margin:0;color:#dbeafe;font-size:14px;}
.fh-stats{display:flex;gap:10px;flex-wrap:wrap;margin:4px 0;font-family:Arial,sans-serif;}
.fh-stat{background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;border-radius:10px;
  padding:8px 16px;min-width:110px;}
.fh-stat b{display:block;font-size:22px;color:#0b3c5d;}
.fh-stat span{font-size:12px;color:#475569;}
.fh-card{border:1px solid #cbd5e1;border-radius:12px;padding:14px;}
.fh-msg{padding:8px 12px;border-radius:8px;font:14px Arial,sans-serif;margin-top:6px;}
.fh-ok{background:#dcfce7;color:#14532d;}
.fh-err{background:#fee2e2;color:#7f1d1d;}
.fh-info{background:#e0f2fe;color:#0c4a6e;}
.fh-warn{background:#fef3c7;color:#78350f;}
.fh-wrap{overflow:auto;max-height:430px;max-width:100%;border:1px solid #cbd5e1;
  border-radius:8px;background:#fff;}
.fh-tbl{border-collapse:collapse;width:100%;font:14px Arial,sans-serif;color:#111827;}
.fh-tbl th{position:sticky;top:0;background:#0b3c5d;color:#fff;text-align:left;
  padding:9px 12px;white-space:nowrap;}
.fh-tbl td{padding:8px 12px;border-bottom:1px solid #e2e8f0;background:#fff;color:#111827;}
.fh-tbl tr:nth-child(even) td{background:#f8fafc;}
.fh-tbl tr:hover td{background:#e0f2fe;}
.fh-tbl tr.fh-new td{background:#fef08a;}
.fh-tbl .num{text-align:right;font-variant-numeric:tabular-nums;}
.fh-empty{color:#64748b;padding:14px;font:14px Arial,sans-serif;}
.fh-cap{color:#64748b;font:12px Arial,sans-serif;margin:6px 2px;}
</style>
"""


def nb_message(kind, text):
    return f"<div class='fh-msg fh-{kind}'>{escape(text)}</div>"


def make_html_table(rows, highlight_trip=None):
    if not rows:
        return NB_CSS + "<div class='fh-empty'>No records to display.</div>"
    columns = list(rows[0].keys())
    numeric = {c for c in columns if "Quantity" in c}
    head = "".join(
        f"<th class='{'num' if c in numeric else ''}'>{escape(str(c))}</th>"
        for c in columns
    )
    body = []
    for row in rows:
        is_new = highlight_trip is not None and row.get("Trip ID") == highlight_trip
        cells = "".join(
            f"<td class='{'num' if c in numeric else ''}'>"
            f"{escape(format_cell(row.get(c, '')))}</td>"
            for c in columns
        )
        body.append(f"<tr{' class=fh-new' if is_new else ''}>{cells}</tr>")
    return (
        NB_CSS
        + "<div class='fh-wrap'><table class='fh-tbl'>"
        + f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
        + f"</table></div><div class='fh-cap'>{len(rows)} row(s)</div>"
    )


# ---------------------------------------------------------------------
# NOTEBOOK / COLAB GUI
# ---------------------------------------------------------------------

def run_notebook_gui():
    # Colab sometimes needs its custom widget manager enabled explicitly.
    # In Jupyter / VS Code this import is unavailable, so the block is skipped.
    try:
        from google.colab import output
        output.enable_custom_widget_manager()
    except (ImportError, AttributeError):
        pass

    import ipywidgets as widgets
    from IPython.display import display

    full = widgets.Layout(width="100%")
    label_style = {"description_width": "95px"}

    banner = widgets.HTML(
        NB_CSS
        + "<div class='fh-banner'><h2>🎣 Fisheries Harbour &amp; Catch Dashboard</h2>"
        "<p>Record fishing trips, manage catch data, and inspect the live database.</p></div>"
    )
    stats = widgets.HTML()

    # ---- Insert card ----
    harbour = widgets.Text(description="Harbour:", placeholder="e.g. Kochi Harbour",
                           layout=full, style=label_style)
    boat = widgets.Text(description="Boat:", placeholder="e.g. Sea Falcon",
                        layout=full, style=label_style)
    catch_type = widgets.Text(description="Catch type:", placeholder="e.g. Tuna (kg)",
                              layout=full, style=label_style)
    quantity = widgets.Text(description="Quantity:", placeholder="e.g. 125.5",
                            layout=full, style=label_style)
    add_button = widgets.Button(description="Add Record", button_style="success",
                                icon="plus", layout=widgets.Layout(width="160px"))
    add_message = widgets.HTML()
    insert_card = widgets.VBox(
        [widgets.HTML("<h3 style='margin:0 0 8px 0'>➕ Insert a trip and catch</h3>"),
         harbour, boat, catch_type, quantity, add_button, add_message],
        layout=widgets.Layout(flex="1 1 360px", min_width="300px", margin="0 12px 12px 0"),
    )
    insert_card.add_class("fh-card")

    # ---- Delete card ----
    entity = widgets.Dropdown(options=["Harbour", "Fishing Trip", "Catch Record"],
                              value="Harbour", description="Delete:",
                              layout=full, style=label_style)
    record_choice = widgets.Dropdown(options=[], description="Record:",
                                     layout=full, style=label_style)
    delete_hint = widgets.HTML()
    delete_button = widgets.Button(description="Delete Selected", button_style="danger",
                                   icon="trash", layout=widgets.Layout(width="160px"))
    delete_message = widgets.HTML()
    delete_card = widgets.VBox(
        [widgets.HTML("<h3 style='margin:0 0 8px 0'>🗑️ Delete records</h3>"),
         entity, record_choice, delete_hint, delete_button, delete_message],
        layout=widgets.Layout(flex="1 1 360px", min_width="300px", margin="0 0 12px 0"),
    )
    delete_card.add_class("fh-card")

    # ---- Tabs ----
    tab_names = ["Joined View", "Harbours", "Fishing Trips", "Catch Records"]
    tab_outputs = [widgets.HTML() for _ in tab_names]
    tabs = widgets.Tab(children=tab_outputs)
    for i, name in enumerate(tab_names):
        tabs.set_title(i, name)

    last_added = {"trip": None}

    def refresh_tables():
        data = get_table_data()
        for i, (pane, rows) in enumerate(zip(tab_outputs, data)):
            pane.value = make_html_table(rows, last_added["trip"])
            tabs.set_title(i, f"{tab_names[i]} ({len(rows)})")
        stats.value = (
            "<div class='fh-stats'>"
            f"<div class='fh-stat'><b>{len(data[1])}</b><span>Harbours</span></div>"
            f"<div class='fh-stat'><b>{len(data[2])}</b><span>Fishing trips</span></div>"
            f"<div class='fh-stat'><b>{len(data[3])}</b><span>Catch records</span></div>"
            "</div>"
        )

    def update_hint(*_):
        if record_choice.value is None:
            delete_hint.value = ""
        else:
            delete_hint.value = nb_message(
                "warn", get_cascade_summary(entity.value, record_choice.value))

    def refresh_delete_choices(*_):
        options = get_delete_options(entity.value)
        record_choice.options = [(item["label"], item["id"]) for item in options]
        record_choice.value = options[0]["id"] if options else None
        record_choice.disabled = not bool(options)
        delete_button.disabled = not bool(options)
        update_hint()

    def on_add(_):
        try:
            trip_id = add_trip_and_catch(
                harbour.value, boat.value, catch_type.value, quantity.value
            )
            # Clear all insert fields after a successful transaction.
            for field in (harbour, boat, catch_type, quantity):
                field.value = ""
            last_added["trip"] = trip_id
            delete_message.value = ""
            add_message.value = nb_message(
                "ok", f"Added trip {trip_id} and its catch record (highlighted below).")
            tabs.selected_index = 0
            refresh_tables()
            refresh_delete_choices()
        except Exception as exc:
            add_message.value = nb_message("err", str(exc))

    def on_delete(_):
        if record_choice.value is None:
            delete_message.value = nb_message("err", "No record is available to delete.")
            return
        try:
            delete_record(entity.value, record_choice.value)
            last_added["trip"] = None
            add_message.value = ""
            delete_message.value = nb_message("ok", f"{entity.value} deleted successfully.")
            refresh_tables()
            refresh_delete_choices()  # Never retain a deleted ID in the selector.
        except Exception as exc:
            delete_message.value = nb_message("err", str(exc))
            refresh_tables()
            refresh_delete_choices()

    add_button.on_click(on_add)
    entity.observe(refresh_delete_choices, names="value")
    record_choice.observe(update_hint, names="value")
    delete_button.on_click(on_delete)

    refresh_tables()
    refresh_delete_choices()
    forms = widgets.HBox([insert_card, delete_card],
                         layout=widgets.Layout(flex_flow="row wrap", width="100%"))
    display(widgets.VBox([banner, stats, widgets.HTML("<div style='height:8px'></div>"),
                          forms, tabs]))


# ---------------------------------------------------------------------
# DESKTOP GUI (TKINTER)
# ---------------------------------------------------------------------

def run_tkinter_gui():
    import tkinter as tk
    from tkinter import ttk

    NAVY, SKY = "#0b3c5d", "#dbeafe"
    OK, ERR, MUTED = "#15803d", "#b91c1c", "#64748b"

    root = tk.Tk()
    root.title("Fisheries Harbour & Catch Dashboard")
    root.geometry("1150x760")
    root.minsize(900, 620)

    style = ttk.Style(root)
    if "clam" in style.theme_names() and root.tk.call("tk", "windowingsystem") == "x11":
        style.theme_use("clam")  # nicer than the bare default on Linux
    style.configure("Treeview", rowheight=26, font=("Arial", 10))
    style.configure("Treeview.Heading", font=("Arial", 10, "bold"))
    style.configure("Card.TLabelframe.Label", font=("Arial", 11, "bold"))
    style.configure("Hint.TLabel", foreground=MUTED, font=("Arial", 9))

    # ---- Header banner ----
    banner = tk.Frame(root, bg=NAVY)
    banner.pack(fill="x")
    tk.Label(banner, text="🎣  Fisheries Harbour & Catch Dashboard", bg=NAVY, fg="white",
             font=("Arial", 18, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
    tk.Label(banner, text="Record fishing trips, manage catch data, and inspect the live database.",
             bg=NAVY, fg=SKY, font=("Arial", 10)).pack(anchor="w", padx=16, pady=(0, 12))

    main = ttk.Frame(root, padding=12)
    main.pack(fill="both", expand=True)

    top = ttk.Frame(main)
    top.pack(fill="x")
    top.columnconfigure(0, weight=1, uniform="cards")
    top.columnconfigure(1, weight=1, uniform="cards")

    # ---- Insert card ----
    insert = ttk.LabelFrame(top, text="➕ Insert a trip and catch", padding=12,
                            style="Card.TLabelframe")
    insert.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    insert.columnconfigure(1, weight=1)
    fields = {}
    field_specs = [
        ("Harbour Name", "e.g. Kochi Harbour"),
        ("Boat Name", "e.g. Sea Falcon"),
        ("Catch Type", "e.g. Tuna (kg)"),
        ("Catch Quantity", "e.g. 125.5"),
    ]
    for row, (label, hint) in enumerate(field_specs):
        ttk.Label(insert, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=4)
        entry = ttk.Entry(insert)
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)
        ttk.Label(insert, text=hint, style="Hint.TLabel").grid(
            row=row, column=2, sticky="w", padx=5)
        fields[label] = entry
    status = ttk.Label(insert, text="", wraplength=420, justify="left")
    status.grid(row=len(field_specs) + 1, column=0, columnspan=3, sticky="w", padx=5)

    # ---- Delete card ----
    delete = ttk.LabelFrame(top, text="🗑️ Delete records", padding=12,
                            style="Card.TLabelframe")
    delete.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    delete.columnconfigure(1, weight=1)
    delete_entity = tk.StringVar(value="Harbour")
    delete_item = tk.StringVar()
    ttk.Label(delete, text="Record type").grid(row=0, column=0, sticky="w", padx=5, pady=4)
    entity_box = ttk.Combobox(delete, textvariable=delete_entity,
                              values=["Harbour", "Fishing Trip", "Catch Record"],
                              state="readonly")
    entity_box.grid(row=0, column=1, sticky="ew", padx=5, pady=4)
    ttk.Label(delete, text="Select record").grid(row=1, column=0, sticky="w", padx=5, pady=4)
    item_box = ttk.Combobox(delete, textvariable=delete_item, state="readonly")
    item_box.grid(row=1, column=1, sticky="ew", padx=5, pady=4)
    hint_label = ttk.Label(delete, text="", style="Hint.TLabel", wraplength=420, justify="left")
    hint_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=5)
    delete_status = ttk.Label(delete, text="", wraplength=420, justify="left")
    delete_status.grid(row=4, column=0, columnspan=2, sticky="w", padx=5)

    # ---- Tabs ----
    notebook = ttk.Notebook(main)
    notebook.pack(fill="both", expand=True, pady=(10, 4))
    tree_views = {}
    view_columns = {
        "Joined View": ["Trip ID", "Harbour Name", "Boat Name",
                        "Departure Date", "Catch Type", "Catch Quantity"],
        "Harbours": ["Harbour ID", "Harbour Name", "Contact Email"],
        "Fishing Trips": ["Trip ID", "Harbour ID", "Boat Name", "Departure Date"],
        "Catch Records": ["Catch ID", "Trip ID", "Catch Type", "Catch Quantity"],
    }
    for tab_name, columns in view_columns.items():
        frame = ttk.Frame(notebook, padding=5)
        notebook.add(frame, text=tab_name)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            is_id = col.endswith("ID")
            is_num = "Quantity" in col
            tree.heading(col, text=col)
            tree.column(col, width=90 if is_id else 170,
                        anchor="e" if is_num else ("center" if is_id else "w"))
        tree.tag_configure("odd", background="#f1f5f9")
        tree.tag_configure("new", background="#fef08a")
        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree_views[tab_name] = tree

    counts = tk.StringVar()
    ttk.Label(main, textvariable=counts, style="Hint.TLabel").pack(anchor="w")

    last_added = {"trip": None}

    def refresh_tables():
        data = get_table_data()
        for i, ((tab_name, tree), rows) in enumerate(zip(tree_views.items(), data)):
            tree.delete(*tree.get_children())
            for n, row in enumerate(rows):
                tags = ["odd"] if n % 2 else []
                if last_added["trip"] is not None and row.get("Trip ID") == last_added["trip"]:
                    tags = ["new"]
                tree.insert("", "end", values=[format_cell(v) for v in row.values()],
                            tags=tags)
            notebook.tab(i, text=f"{tab_name} ({len(rows)})")
        counts.set(f"{len(data[1])} harbour(s)  ·  {len(data[2])} trip(s)  ·  "
                   f"{len(data[3])} catch record(s)")

    def selected_option():
        selected = delete_item.get()
        return next((x for x in get_delete_options(delete_entity.get())
                     if x["label"] == selected), None)

    def update_hint(*_):
        option = selected_option()
        hint_label.configure(
            text=get_cascade_summary(delete_entity.get(), option["id"]) if option else "")

    def refresh_delete_choices(*_):
        options = get_delete_options(delete_entity.get())
        labels = [item["label"] for item in options]
        item_box["values"] = labels
        delete_item.set(labels[0] if labels else "")
        item_box.configure(state="readonly" if labels else "disabled")
        delete_button.configure(state="normal" if labels else "disabled")
        update_hint()

    def say(label, text, ok):
        label.configure(text=text, foreground=OK if ok else ERR)

    def add_from_desktop(_event=None):
        try:
            trip_id = add_trip_and_catch(
                fields["Harbour Name"].get(),
                fields["Boat Name"].get(),
                fields["Catch Type"].get(),
                fields["Catch Quantity"].get()
            )
        except Exception as exc:
            say(status, str(exc), ok=False)
            return
        for entry in fields.values():
            entry.delete(0, tk.END)
        last_added["trip"] = trip_id
        say(status, f"Added trip {trip_id} and its catch record (highlighted).", ok=True)
        delete_status.configure(text="")
        refresh_tables()
        refresh_delete_choices()
        notebook.select(0)
        fields["Harbour Name"].focus_set()

    def delete_from_desktop():
        option = selected_option()
        if option is None:
            say(delete_status, "Choose an existing record first.", ok=False)
            refresh_delete_choices()
            return
        try:
            delete_record(delete_entity.get(), option["id"])
        except Exception as exc:
            say(delete_status, str(exc), ok=False)
            refresh_tables()
            refresh_delete_choices()
            return
        last_added["trip"] = None
        status.configure(text="")
        say(delete_status, f"{delete_entity.get()} deleted.", ok=True)
        refresh_tables()
        refresh_delete_choices()

    ttk.Button(insert, text="Add Record", command=add_from_desktop).grid(
        row=len(field_specs), column=1, sticky="w", padx=5, pady=8
    )
    delete_button = ttk.Button(delete, text="Delete Selected", command=delete_from_desktop)
    delete_button.grid(row=3, column=1, sticky="w", padx=5, pady=8)
    entity_box.bind("<<ComboboxSelected>>", refresh_delete_choices)
    item_box.bind("<<ComboboxSelected>>", update_hint)
    for entry in fields.values():
        entry.bind("<Return>", add_from_desktop)  # Enter submits the form

    refresh_tables()
    refresh_delete_choices()
    fields["Harbour Name"].focus_set()
    root.mainloop()


# ---------------------------------------------------------------------
# COMMAND-LINE FALLBACK
# ---------------------------------------------------------------------

def run_cli():
    try:
        _cli_loop()
    except (EOFError, KeyboardInterrupt):
        print("\nInput closed. Exiting.")


def _cli_loop():
    print("\nFisheries Harbour & Catch Dashboard — CLI mode")
    print("No graphical display is available; database operations remain usable.")
    while True:
        print("\n1. Add trip + catch  2. View joined records  3. Delete  4. Exit")
        choice = input("Choose: ").strip()
        if choice == "1":
            try:
                trip = add_trip_and_catch(
                    input("Harbour name: "),
                    input("Boat name: "),
                    input("Catch type: "),
                    input("Catch quantity: "),
                )
                print(f"Added trip {trip}.")
            except Exception as exc:
                print("Error:", exc)
        elif choice == "2":
            for row in get_table_data()[0]:
                print(row)
        elif choice == "3":
            entity = input("Delete Harbour, Fishing Trip, or Catch Record: ").strip()
            if entity not in ("Harbour", "Fishing Trip", "Catch Record"):
                print("Invalid record type.")
                continue
            options = get_delete_options(entity)
            if not options:
                print("No records available.")
                continue
            for item in options:
                print(f"{item['id']}: {item['label']}")
            try:
                record_id = int(input("Enter ID: "))
                delete_record(entity, record_id)
                print("Deleted.")
            except Exception as exc:
                print("Error:", exc)
        elif choice == "4":
            break
        else:
            print("Choose 1, 2, 3, or 4.")


def in_notebook():
    try:
        shell = get_ipython().__class__.__name__
        return shell in ("ZMQInteractiveShell", "Shell")
    except Exception:
        return False


def main():
    initialize_database()

    if in_notebook():
        try:
            run_notebook_gui()
            return
        except Exception as exc:
            print("Notebook GUI could not start:", exc)
            print("Falling back to command-line mode.")

    # Normal Python script: use Tkinter only if a display is available.
    if (os.name == "nt" or sys.platform == "darwin"
            or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            run_tkinter_gui()
            return
        except Exception as exc:
            print("Desktop GUI could not start:", exc)
            print("Falling back to command-line mode.")

    run_cli()


if __name__ == "__main__":
    main()
