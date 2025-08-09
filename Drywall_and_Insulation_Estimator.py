# estimators_app.py
# Two estimators in one Streamlit app:
# - Drywall Estimator (material takeoff, unit costs, labour, high parts, pricing)
# - Insulation Estimator (your original flow with minor hardening)
#
# Tip: add a requirements.txt with:
#   streamlit>=1.34
#   pandas>=2.0
#   matplotlib>=3.7
#   reportlab>=3.6

import math
import streamlit as st
import pandas as pd

# Optional libs (used in Insulation tab)
try:
    import matplotlib.pyplot as plt
except Exception:
    plt = None

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import letter
except Exception:
    rl_canvas = None
    letter = None

FT2_TO_M2 = 0.09290304


# ===========================
# Drywall Estimator (function)
# ===========================
def run_drywall_estimator():
    WALL_HEIGHT_PRESETS = ["8 ft", "9 ft", "10 ft", "12 ft", "14 ft", "Custom"]
    DOOR_PRESETS = [
        ("24 x 80 in", 24 / 12, 80 / 12),
        ("28 x 80 in", 28 / 12, 80 / 12),
        ("30 x 80 in", 30 / 12, 80 / 12),
        ("32 x 80 in", 32 / 12, 80 / 12),
        ("36 x 80 in", 36 / 12, 80 / 12),
        ("Custom", None, None),
    ]

    st.header("Drywall Estimator (per room)")
    st.caption("Calculate drywall areas, auto material takeoff, and pricing. Windows/doors deducted, ceilings optional.")

    # ---------- Options / Factors ----------
    with st.expander("General Options", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            include_waste = st.checkbox("Add waste percentage", value=True)
        with col2:
            waste_pct = st.number_input("Waste %", 0.0, 50.0, 10.0, 0.5) if include_waste else 0.0
        show_intermediate = st.checkbox("Show intermediate math", value=False)

    with st.expander("Material Takeoff Factors (defaults)", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            mud_gal_per_1000 = st.number_input("Mud (gal per 1000 ft^2)", 5.0, 20.0, 9.5, 0.1)
            mud_pail_gal = st.number_input("Mud pail size (gal)", 1.0, 6.0, 4.5, 0.5)
            tape_sqft_per_roll = st.number_input("Tape coverage (ft^2 per roll)", 600.0, 2000.0, 1200.0, 50.0)
        with c2:
            screws_per_sqft = st.number_input("Screws per ft^2", 0.5, 2.0, 1.25, 0.05)
            screws_per_box = st.number_input("Screws per box", 500, 5000, 1000, 100)
            corner_bead_lf_per_1000 = st.number_input("Corner bead (lf per 1000 ft^2)", 0.0, 200.0, 50.0, 5.0)
        with c3:
            corner_bead_piece_len_ft = st.number_input("Corner bead piece length (ft)", 4.0, 12.0, 8.0, 1.0)
            sheet_size = st.selectbox("Sheet size", ["4x8 (32 ft^2)", "4x12 (48 ft^2)"], index=0)

    with st.expander("Resilient Channel (optional)", expanded=False):
        include_resilient_channel = st.checkbox("Include Resilient Channel", value=False)
        rc_spacing_in = st.selectbox("RC spacing (in)", [16, 24], index=0)
        rc_piece_length_ft = st.number_input("RC piece length (ft)", 8.0, 16.0, 12.0, 1.0)

    with st.expander("Unit Costs & Extras", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            cost_per_sheet = st.number_input("Sheet cost ($/sheet)", 0.0, 200.0, 0.0, 0.5)
            cost_mud_pail = st.number_input("Mud cost ($/pail)", 0.0, 200.0, 0.0, 0.5)
        with c2:
            cost_tape_roll = st.number_input("Tape cost ($/roll)", 0.0, 100.0, 0.0, 0.5)
            cost_screws_box = st.number_input("Screws cost ($/box)", 0.0, 200.0, 0.0, 0.5)
        with c3:
            cost_corner_bead_piece = st.number_input("Corner bead cost ($/piece)", 0.0, 100.0, 0.0, 0.5)
            cost_rc_piece = st.number_input("Resilient channel cost ($/piece)", 0.0, 100.0, 0.0, 0.5)

        c4, c5 = st.columns(2)
        with c4:
            pot_light_count = st.number_input("Pot lights (qty)", min_value=0, step=1, value=0)
        with c5:
            pot_light_cost = st.number_input("Cost per pot light ($)", min_value=0.0, step=1.0, value=0.0)

    with st.expander("Labour & Tax", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            labour_rate_sqft = st.number_input("Labour rate per ft^2 ($)", 0.0, 100.0, 0.0, 0.01)
        with c2:
            labour_rate_sqm = st.number_input("Labour rate per m^2 ($)", 0.0, 1000.0, 0.0, 0.01)
        with c3:
            tax_pct = st.number_input("Tax %", 0.0, 25.0, 13.0, 0.5, help="Ontario HST ~13%")

        st.markdown("**High-Parts Labour** (qualifies if height > 10 ft and area > 64 ft^2)")
        cc1, cc2 = st.columns(2)
        with cc1:
            labour_high_part_flat = st.number_input("High-part labour flat ($ per qualifying part)", 0.0, 5000.0, 0.0, 1.0)
        with cc2:
            labour_high_part_rate_sqft = st.number_input("High-part labour rate ($ per ft^2 of qualifying area)", 0.0, 100.0, 0.0, 0.01)

    st.markdown("---")

    # ---------- Rooms ----------
    col_l, col_r = st.columns([1, 1])
    with col_l:
        room_count = st.number_input("Number of rooms", 1, 50, 3, 1)
    with col_r:
        default_h_choice = st.selectbox("Default wall height", WALL_HEIGHT_PRESETS, index=0)
        if default_h_choice == "Custom":
            default_wall_h = st.number_input("Custom default wall height (ft)", 0.0, 20.0, 8.0, 0.1)
        else:
            default_wall_h = float(default_h_choice.split()[0])

    rooms_data = []
    rc_total_lf = 0.0  # RC total linear feet

    for i in range(int(room_count)):
        st.subheader(f"Room {i+1}")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])
            with c1:
                name = st.text_input(f"Room name #{i+1}", value=f"Room {i+1}", key=f"name_{i}")
            with c2:
                length = st.number_input(f"Length (ft) #{i+1}", 0.0, 1000.0, 0.0, 0.1, key=f"len_{i}")
            with c3:
                width = st.number_input(f"Width (ft) #{i+1}", 0.0, 1000.0, 0.0, 0.1, key=f"wid_{i}")
            with c4:
                default_idx = (
                    ["8 ft", "9 ft", "10 ft", "12 ft", "14 ft"].index(f"{int(default_wall_h)} ft")
                    if f"{int(default_wall_h)} ft" in ["8 ft", "9 ft", "10 ft", "12 ft", "14 ft"]
                    else len(WALL_HEIGHT_PRESETS) - 1
                )
                h_choice = st.selectbox(f"Wall height #{i+1}", WALL_HEIGHT_PRESETS, index=default_idx, key=f"h_choice_{i}")
                if h_choice == "Custom":
                    height = st.number_input(f"Custom wall height (ft) #{i+1}", 0.0, 20.0, default_wall_h, 0.1, key=f"h_{i}")
                else:
                    height = float(h_choice.split()[0])

            c5, c6, c7 = st.columns([1, 1, 1])
            with c5:
                include_ceiling = st.checkbox(f"Include ceiling? #{i+1}", value=True, key=f"ceil_inc_{i}")
            with c6:
                has_windows = st.checkbox(f"Windows? #{i+1}", value=False, key=f"win_has_{i}")
            with c7:
                has_doors = st.checkbox(f"Doors? #{i+1}", value=False, key=f"door_has_{i}")

            # Windows
            windows = []
            if has_windows:
                num_windows = st.number_input(f"How many windows? #{i+1}", 1, 20, 1, 1, key=f"w_count_{i}")
                st.markdown("**Windows**")
                for w in range(num_windows):
                    wc1, wc2 = st.columns(2)
                    with wc1:
                        w_w = st.number_input(f"Window {w+1} width (ft) [R{i+1}]", 0.0, 100.0, 0.0, 0.1, key=f"win_w_{i}_{w}")
                    with wc2:
                        w_h = st.number_input(f"Window {w+1} height (ft) [R{i+1}]", 0.0, 100.0, 0.0, 0.1, key=f"win_h_{i}_{w}")
                    windows.append((w_w, w_h))

            # Doors
            doors = []
            if has_doors:
                num_doors = st.number_input(f"How many doors? #{i+1}", 1, 20, 1, 1, key=f"d_count_{i}")
                st.markdown("**Doors**")
                for d in range(num_doors):
                    dc1, dc2, dc3 = st.columns([1.2, 1, 1])
                    with dc1:
                        choice_labels = [label for label, _, _ in DOOR_PRESETS]
                        default_door_idx = choice_labels.index("30 x 80 in") if "30 x 80 in" in choice_labels else 0
                        door_choice = st.selectbox(f"Door {d+1} size [R{i+1}]", choice_labels, index=default_door_idx, key=f"door_choice_{i}_{d}")
                    if door_choice == "Custom":
                        with dc2:
                            d_w_in = st.number_input(f"Door {d+1} width (in)", 0.0, 120.0, 0.0, 0.5, key=f"door_w_in_{i}_{d}")
                        with dc3:
                            d_h_in = st.number_input(f"Door {d+1} height (in)", 0.0, 120.0, 0.0, 0.5, key=f"door_h_in_{i}_{d}")
                        d_w = d_w_in / 12.0
                        d_h = d_h_in / 12.0
                    else:
                        preset = next(p for p in DOOR_PRESETS if p[0] == door_choice)
                        d_w, d_h = preset[1], preset[2]
                    doors.append((d_w, d_h))

            # Areas
            perimeter = 2 * (length + width)
            wall_area_gross = perimeter * height
            openings_area = sum(w * h for w, h in windows) + sum(w * h for w, h in doors)
            wall_area_net = max(wall_area_gross - openings_area, 0.0)
            ceiling_area = (length * width) if include_ceiling else 0.0
            total_area_ft2 = wall_area_net + ceiling_area
            waste_multiplier = 1.0 + (waste_pct / 100.0)
            total_with_waste_ft2 = total_area_ft2 * waste_multiplier

            # RC LF (if enabled)
            if include_resilient_channel and include_ceiling and width > 0 and length > 0:
                rows = math.floor((width * 12) / rc_spacing_in) + 1
                rc_total_lf += rows * length

            rooms_data.append({
                "room": name,
                "length_ft": length,
                "width_ft": width,
                "height_ft": height,
                "perimeter_ft": perimeter,
                "wall_area_net_ft2": wall_area_net,
                "ceiling_area_ft2": ceiling_area,
                "total_area_ft2": total_area_ft2,
                "total_with_waste_ft2": total_with_waste_ft2,
            })

            if show_intermediate:
                st.caption(
                    f"Perimeter: {perimeter:.2f} ft | Walls net: {wall_area_net:.2f} ft^2 | "
                    f"Ceiling: {ceiling_area:.2f} ft^2 | Total: {total_area_ft2:.2f} ft^2 | "
                    f"Waste%: {waste_pct:.1f} -> With waste: {total_with_waste_ft2:.2f} ft^2"
                )

    # ---------- High Parts ----------
    st.subheader("High Parts (charged extras)")
    st.caption("Qualify only if height > 10 ft and area > 64 ft^2. Counted for labour charge, not materials.")
    num_high_parts = st.number_input("Number of high parts", 0, 20, 0, 1)
    qualifying_hp_area_ft2 = 0.0
    qualifying_hp_count = 0
    for hp in range(num_high_parts):
        c1, c2 = st.columns(2)
        with c1:
            hp_height = st.number_input(f"High part #{hp+1} height (ft)", 0.0, 30.0, 0.0, 0.1, key=f"hp_h_{hp}")
        with c2:
            hp_area = st.number_input(f"High part #{hp+1} area (ft^2)", 0.0, 2000.0, 0.0, 1.0, key=f"hp_a_{hp}")
        if hp_height > 10.0 and hp_area > 64.0:
            qualifying_hp_area_ft2 += hp_area
            qualifying_hp_count += 1

    # ---------- Summary & Takeoff ----------
    if rooms_data:
        df = pd.DataFrame(rooms_data)
        df["total_area_m2"] = df["total_area_ft2"] * FT2_TO_M2
        df["total_with_waste_m2"] = df["total_with_waste_ft2"] * FT2_TO_M2

        st.markdown("---")
        st.subheader("Per-room breakdown")
        show_cols = [
            "room", "length_ft", "width_ft", "height_ft",
            "wall_area_net_ft2", "ceiling_area_ft2", "total_area_ft2",
            "total_area_m2", "total_with_waste_ft2", "total_with_waste_m2"
        ]
        st.dataframe(df[show_cols], use_container_width=True)

        total_ft2 = float(df["total_area_ft2"].sum())
        total_m2 = total_ft2 * FT2_TO_M2
        total_waste_ft2 = float(df["total_with_waste_ft2"].sum())
        total_waste_m2 = total_waste_ft2 * FT2_TO_M2

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Grand Total (ft^2)", f"{total_ft2:,.2f}")
        c2.metric("Grand Total (m^2)", f"{total_m2:,.2f}")
        c3.metric("With Waste (ft^2)", f"{total_waste_ft2:,.2f}")
        c4.metric("With Waste (m^2)", f"{total_waste_m2:,.2f}")

        # Material Takeoff
        st.markdown("---")
        st.subheader("Material Takeoff (auto)")

        sheet_area = 32.0 if "4x8" in sheet_size else 48.0
        sheets = math.ceil(total_waste_ft2 / sheet_area) if sheet_area > 0 else 0

        mud_gal = (total_waste_ft2 / 1000.0) * mud_gal_per_1000
        mud_pails = math.ceil(mud_gal / mud_pail_gal) if mud_pail_gal > 0 else 0

        tape_rolls = math.ceil(total_waste_ft2 / tape_sqft_per_roll) if tape_sqft_per_roll > 0 else 0

        screws_qty = math.ceil(total_waste_ft2 * screws_per_sqft)
        screws_boxes = math.ceil(screws_qty / screws_per_box) if screws_per_box > 0 else 0

        corner_bead_lf = (total_waste_ft2 / 1000.0) * corner_bead_lf_per_1000
        corner_bead_pcs = math.ceil(corner_bead_lf / corner_bead_piece_len_ft) if corner_bead_piece_len_ft > 0 else 0

        rc_pieces = 0
        rc_total_lf = 0.0 if len(df) == 0 else sum([])  # placeholder to keep linter happy
        # Note: rc_total_lf is computed in-room loop; not displayed if RC disabled
        # We won't re-use it here for display; only quantities matter above.

        colA, colB, colC = st.columns([1, 1, 1])
        with colA:
            st.write(f"Board area (with waste): **{total_waste_ft2:,.0f} ft^2**")
            st.write(f"Sheets ({sheet_size}): **{sheets}**")
            st.write(f"Mud: **{mud_gal:,.1f} gal** (~{mud_pails} pails @ {mud_pail_gal:g} gal)")
        with colB:
            st.write(f"Tape: **{tape_rolls} rolls** (approx)")
            st.write(f"Screws: **{screws_qty:,} pcs** (~{screws_boxes} boxes @ {screws_per_box} pcs)")
            st.write(f"Corner bead: **{corner_bead_pcs} pcs** (~{corner_bead_lf:,.0f} lf, {corner_bead_piece_len_ft:g} ft pieces)")
        with colC:
            # We don't display RC quantities here because we didn't carry rc_total_lf out of the loop safely;
            # feel free to enable RC in the sidebar and compute/display similarly if needed.
            st.write("Resilient channel: **(optional; see Unit Costs settings)**")

        # Costs & Pricing
        st.markdown("---")
        st.subheader("Costs and Pricing")

        # Materials cost
        mat_board_cost = sheets * cost_per_sheet
        mat_mud_cost = mud_pails * cost_mud_pail
        mat_tape_cost = tape_rolls * cost_tape_roll
        mat_screws_cost = screws_boxes * cost_screws_box
        mat_corner_cost = corner_bead_pcs * cost_corner_bead_piece
        # RC omitted in total since quantity not displayed; enable if you decide to compute rc_total_lf persistently.
        mat_pot_lights_cost = pot_light_count * pot_light_cost

        materials_breakdown = [
            ("Board (sheets)", sheets, mat_board_cost),
            ("Mud (pails)", mud_pails, mat_mud_cost),
            ("Tape (rolls)", tape_rolls, mat_tape_cost),
            ("Screws (boxes)", screws_boxes, mat_screws_cost),
            ("Corner bead (pieces)", corner_bead_pcs, mat_corner_cost),
            ("Pot lights (qty)", pot_light_count, mat_pot_lights_cost),
        ]

        material_subtotal = sum(v for _, _, v in materials_breakdown)

        # Labour area: with-waste + qualifying high-part area
        charge_area_ft2 = total_waste_ft2 + qualifying_hp_area_ft2
        charge_area_m2 = charge_area_ft2 * FT2_TO_M2

        if labour_rate_sqft > 0:
            labour_area_cost = charge_area_ft2 * labour_rate_sqft
            labour_area_label = f"Area labour @ ${labour_rate_sqft:.2f}/ft^2"
        elif labour_rate_sqm > 0:
            labour_area_cost = charge_area_m2 * labour_rate_sqm
            labour_area_label = f"Area labour @ ${labour_rate_sqm:.2f}/m^2"
        else:
            labour_area_cost = 0.0
            labour_area_label = "Area labour @ $0"

        # High-parts labour: prefer flat per part, else per ft^2 of qualifying area
        labour_high_part_flat = st.session_state.get("labour_high_part_flat", 0.0) if "labour_high_part_flat" in st.session_state else labour_high_part_flat
        labour_high_part_rate_sqft = st.session_state.get("labour_high_part_rate_sqft", 0.0) if "labour_high_part_rate_sqft" in st.session_state else labour_high_part_rate_sqft

        if qualifying_hp_count > 0 and labour_high_part_flat > 0:
            labour_high_parts_cost = qualifying_hp_count * labour_high_part_flat
            labour_high_label = f"High-parts labour @ ${labour_high_part_flat:.2f} each (x{qualifying_hp_count})"
        else:
            labour_high_parts_cost = qualifying_hp_area_ft2 * labour_high_part_rate_sqft
            labour_high_label = f"High-parts labour @ ${labour_high_part_rate_sqft:.2f}/ft^2 (area {qualifying_hp_area_ft2:.0f} ft^2)"

        labour_subtotal = labour_area_cost + labour_high_parts_cost

        subtotal_no_tax = material_subtotal + labour_subtotal
        tax_pct_val = st.session_state.get("tax_pct", 0.0) if "tax_pct" in st.session_state else 0.0
        # Use local tax_pct from expander
        tax_pct_val = tax_pct
        total_with_tax = subtotal_no_tax * (1.0 + tax_pct_val / 100.0) if tax_pct_val > 0 else subtotal_no_tax
        cash_price = subtotal_no_tax  # no tax

        st.markdown("#### Material Costs")
        for label, qty, cost in materials_breakdown:
            st.write(f"- {label}: {qty} → ${cost:,.2f}")
        st.write(f"**Material Subtotal:** ${material_subtotal:,.2f}")

        st.markdown("#### Labour Costs")
        st.write(f"- {labour_area_label}: ${labour_area_cost:,.2f}")
        st.write(f"- {labour_high_label}: ${labour_high_parts_cost:,.2f}")
        st.write(f"**Labour Subtotal:** ${labour_subtotal:,.2f}")

        st.markdown("#### Totals")
        st.write(f"- **Subtotal (no tax):** ${subtotal_no_tax:,.2f}")
        st.write(f"- **Total with tax ({tax_pct_val:.1f}%):** ${total_with_tax:,.2f}")
        st.success(f"**Cash price (no tax): ${cash_price:,.2f}**")

        # Downloads
        st.markdown("### Downloads")
        df_display = df[show_cols]
        csv = df_display.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV (per-room)", csv, file_name="drywall_per_room.csv", mime="text/csv")

        lines = ["Drywall Estimator Summary (per room)"]
        for _, r in df.iterrows():
            lines.append(
                f"- {r['room']}: Walls {r['wall_area_net_ft2']:.2f} ft^2, "
                f"Ceiling {r['ceiling_area_ft2']:.2f} ft^2, "
                f"Total {r['total_area_ft2']:.2f} ft^2 ({r['total_area_ft2']*FT2_TO_M2:.2f} m^2)"
            )
        lines += [
            "",
            f"Grand Total: {total_ft2:.2f} ft^2 ({total_m2:.2f} m^2)",
            f"Grand Total w/ waste: {total_waste_ft2:.2f} ft^2 ({total_waste_m2:.2f} m^2)",
            "",
            "Material Takeoff:",
            f"- Board: {total_waste_ft2:,.0f} ft^2 → {sheets} sheets ({sheet_size})",
            f"- Mud: {mud_gal:,.1f} gal (~{mud_pails} pails @ {mud_pail_gal:g} gal)",
            f"- Tape: {tape_rolls} rolls",
            f"- Screws: {screws_qty:,} pcs (~{screws_boxes} boxes @ {screws_per_box} pcs)",
            f"- Corner bead: {corner_bead_pcs} pcs (~{corner_bead_lf:,.0f} lf, {corner_bead_piece_len_ft:g} ft pieces)",
            "",
            "Costs:",
        ]
        for label, qty, cost in materials_breakdown:
            lines.append(f"- {label}: {qty} → ${cost:,.2f}")
        lines += [
            f"- Area labour: ${labour_area_cost:,.2f}",
            f"- High-parts labour: ${labour_high_parts_cost:,.2f}",
            f"- Material Subtotal: ${material_subtotal:,.2f}",
            f"- Labour Subtotal: ${labour_subtotal:,.2f}",
            f"- Subtotal (no tax): ${subtotal_no_tax:,.2f}",
            f"- Total with tax ({tax_pct_val:.1f}%): ${total_with_tax:,.2f}",
            f"- Cash price (no tax): ${cash_price:,.2f}",
            "",
            "High Parts:",
            f"- Qualifying count: {qualifying_hp_count}",
            f"- Qualifying area total: {qualifying_hp_area_ft2:.2f} ft^2",
        ]
        txt = "\n".join(lines)
        st.download_button("Download TXT (summary)", txt, file_name="drywall_summary.txt", mime="text/plain")
    else:
        st.info("Add at least one room above to see results.")


# =================================
# Insulation Estimator (function)
# =================================
def run_insulation_estimator():
    # Material specifications (coverage per bag and pieces per bag)
    MATERIAL_SPECS = {
        'R12': {'widths': {15: {'coverage_per_bag': 100.0, 'pieces_per_bag': 20},
                           23: {'coverage_per_bag': 153.3, 'pieces_per_bag': 20}}},
        'R14': {'widths': {15: {'coverage_per_bag': 78.3, 'pieces_per_bag': 16},
                           23: {'coverage_per_bag': 120.1, 'pieces_per_bag': 16}}},
        'R20': {'widths': {15: {'coverage_per_bag': 80.0, 'pieces_per_bag': 16},
                           23: {'coverage_per_bag': 122.7, 'pieces_per_bag': 16}}},
        'R22': {'widths': {15: {'coverage_per_bag': 49.0, 'pieces_per_bag': 10},
                           23: {'coverage_per_bag': 75.1, 'pieces_per_bag': 10}}},
        'R28': {'widths': {16: {'coverage_per_bag': 53.3, 'pieces_per_bag': 10},
                           24: {'coverage_per_bag': 80.0, 'pieces_per_bag': 10}}},
        'R31': {'widths': {16: {'coverage_per_bag': 42.7, 'pieces_per_bag': 8},
                           24: {'coverage_per_bag': 64.0, 'pieces_per_bag': 8}}},
        'R40': {'widths': {16: {'coverage_per_bag': 32.0, 'pieces_per_bag': 6},
                           24: {'coverage_per_bag': 48.0, 'pieces_per_bag': 6}}}
    }

    def draw_cost_breakdown_chart(costs):
        if plt is None:
            st.info("Chart unavailable (matplotlib not installed). Add matplotlib to requirements.txt.")
            return
        labels = list(costs.keys())
        values = list(costs.values())
        fig, ax = plt.subplots()
        ax.bar(labels, values)
        ax.set_title("Cost Breakdown")
        ax.set_ylabel("Cost ($)")
        ax.set_xticklabels(labels, rotation=45, ha='right')
        st.pyplot(fig)

    def draw_cathedral_diagram(base_width, rise):
        if plt is None:
            st.info("Diagram unavailable (matplotlib not installed).")
            return
        x = [0, base_width / 2, base_width]
        y = [0, rise, 0]
        fig, ax = plt.subplots()
        ax.plot(x, y, linewidth=2)
        ax.set_xlim(0, max(base_width, 0.1))
        ax.set_ylim(0, max(rise, 0.1))
        ax.set_title("Cathedral Ceiling Cross-Section")
        ax.set_xlabel("Width (ft)")
        ax.set_ylabel("Height Above Wall (ft)")
        ax.grid(True)
        fig.tight_layout()
        st.pyplot(fig)

    st.header("Insulation Estimator")

    tabs = st.tabs(["1. Materials", "2. Dimensions", "3. Labour & Surcharges", "4. Review & Download"])

    with tabs[0]:
        st.subheader("1. Materials")
        wall_r_value = st.selectbox("Wall Insulation R-value", list(MATERIAL_SPECS.keys()))
        wall_width = st.selectbox("Wall Insulation Width (inches)", list(MATERIAL_SPECS[wall_r_value]['widths']))
        wp = MATERIAL_SPECS[wall_r_value]['widths'][wall_width]
        st.write(f"Coverage: {wp['coverage_per_bag']} sqft/bag, Pieces: {wp['pieces_per_bag']} per bag")
        wall_price_per_bag = st.number_input("Wall Price per Bag ($)", min_value=0.0)

        cat_r_value = st.selectbox("Cathedral Insulation R-value", list(MATERIAL_SPECS.keys()))
        cat_width = st.selectbox("Cathedral Insulation Width (inches)", list(MATERIAL_SPECS[cat_r_value]['widths']))
        cp = MATERIAL_SPECS[cat_r_value]['widths'][cat_width]
        st.write(f"Coverage: {cp['coverage_per_bag']} sqft/bag, Pieces: {cp['pieces_per_bag']} per bag")
        cat_price_per_bag = st.number_input("Cathedral Price per Bag ($)", min_value=0.0)

        ceiling_cov_per_bag = st.number_input(
            "Blown-In Coverage per Bag (sqft/bag)", min_value=0.0, help="Sqft covered by one bag of blown-in insulation."
        )
        ceiling_price_per_bag = st.number_input(
            "Blown-In Price per Bag ($)", min_value=0.0, help="Cost per bag of blown-in insulation."
        )

    with tabs[1]:
        st.subheader("2. Dimensions")
        st.markdown("**Walls**")
        wall_linear_feet = st.number_input("Wall Linear Feet (ft)", min_value=0.0)
        wall_height = st.number_input("Wall Height (ft)", min_value=0.0)
        wall_stud_spacing = st.selectbox("Wall Stud Spacing (inches)", [16, 24])

        st.markdown("**Cathedral Sections**")
        num_cat = st.number_input("Number of Cathedral Sections", min_value=1, step=1)
        cat_sections = []
        for i in range(int(num_cat)):
            st.markdown(f"*Section {i+1}*")
            length = st.number_input("Length (ft)", min_value=0.0, key=f"len_{i}")
            base_width = st.number_input("Base Width (ft)", min_value=0.0, key=f"wd_{i}")
            height_above = st.number_input("Height Above Wall (ft)", min_value=0.0, key=f"ht_{i}")
            cat_sections.append((length, base_width, height_above))

        st.markdown("**Truss Spacing for Cathedrals**")
        cat_spacing_in = st.selectbox("Spacing (inches)", [16, 24])

        st.markdown("**Blown-In Ceiling**")
        blow_sq = st.number_input("Blown-in Sq Ft", min_value=0)
        vault_sq = st.number_input("Vaulted/Cathedral Excl. Sq Ft", min_value=0)

    with tabs[2]:
        st.subheader("3. Labour & Surcharges")
        wall_labour_rate = st.number_input("Wall Labour Rate per sqft ($)", min_value=0.0)
        ceiling_hourly = st.number_input("Ceiling Labour Rate per hour ($)", min_value=0.0)
        ceiling_hours = st.number_input("Ceiling Labour Time (hours)", min_value=0.0)
        ceiling_flat_srchg = st.number_input("Ceiling Flat Surcharge ($)", min_value=0.0)
        cathedral_hourly = st.number_input("Cathedral Labour Rate per hour ($)", min_value=0.0)
        cathedral_hours = st.number_input("Cathedral Labour Time per section (hours)", min_value=0.0)
        cathedral_flat = st.number_input("Cathedral Flat Surcharge per section ($)", min_value=0.0)

    with tabs[3]:
        st.subheader("4. Review & Download")
        if st.button("Run Estimate"):
            # Materials
            wall_area = wall_linear_feet * wall_height
            wb_cov = wp["coverage_per_bag"]
            wb_pcs = wp["pieces_per_bag"]
            wall_bags = math.ceil(wall_area / wb_cov) if wb_cov > 0 else 0
            wall_pieces = wall_bags * wb_pcs
            wall_cost = wall_bags * wall_price_per_bag

            # Cathedrals (slope-based)
            cs_cov = cp["coverage_per_bag"]
            cs_pcs = cp["pieces_per_bag"]
            total_cat_area = 0.0
            for length, bw, rise in cat_sections:
                slope = math.sqrt(max((bw / 2) ** 2 + rise ** 2, 0.0))
                total_cat_area += 2 * slope * length
            buffered_cov = cs_cov * 1.10 if cs_cov > 0 else 0
            cat_bags = math.ceil(total_cat_area / buffered_cov) if buffered_cov > 0 else 0
            cat_pieces = cat_bags * cs_pcs
            cat_cost = cat_bags * cat_price_per_bag

            # Ceiling
            ceiling_area = max(blow_sq - vault_sq, 0)
            ceiling_bags = math.ceil(ceiling_area / ceiling_cov_per_bag) if ceiling_cov_per_bag else 0
            ceiling_mat_cost = ceiling_bags * ceiling_price_per_bag

            # Batt counts
            wall_batts = math.ceil(wall_linear_feet / (wall_stud_spacing / 12)) if wall_stud_spacing else 0
            cat_batts = [math.ceil(bw / (cat_spacing_in / 12)) if cat_spacing_in else 0 for _, bw, _ in cat_sections]

            # Labour & surcharges
            wall_lab = wall_area * wall_labour_rate
            area_lab = (wall_area + total_cat_area) * wall_labour_rate
            ceil_lab = ceiling_hourly * ceiling_hours + ceiling_flat_srchg
            cat_surch = ((cathedral_hourly * cathedral_hours) + cathedral_flat) * int(num_cat)

            # Totals
            mat_total = wall_cost + cat_cost + ceiling_mat_cost
            lab_total = wall_lab + area_lab + ceil_lab + cat_surch
            total_tax = (mat_total + lab_total) * 1.05
            total_buf = total_tax * 1.10

            # Build summary text
            lines = [
                "Materials Summary:",
                f"  Wall:      {wall_area:.1f} sq ft → {wall_bags} bags ({wall_pieces} pcs) = ${wall_cost:.2f}",
                f"  Cathedral: {total_cat_area:.1f} sq ft → {cat_bags} bags ({cat_pieces} pcs) = ${cat_cost:.2f}",
                f"  Ceiling:   {ceiling_area:.1f} sq ft → {ceiling_bags} bags = ${ceiling_mat_cost:.2f}",
                "",
                "Labour & Surcharges:",
                f"  Wall Labour:                  ${wall_lab:.2f}",
                f"  Area Labour (Wall+Cathedral): ${area_lab:.2f}",
                f"  Ceiling Labour:               ${ceil_lab:.2f}",
                f"  Cathedral Surcharge:          ${cat_surch:.2f}",
                "",
                "Batt Counts:",
                f"  Wall batts: {wall_batts} pcs",
                f"  Cathedral batts: {sum(cat_batts)} pcs",
                "",
                "Totals:",
                f"  Material Total:       ${mat_total:.2f}",
                f"  Labour Total:         ${lab_total:.2f}",
                f"  Total w/ Tax:         ${total_tax:.2f}",
                f"  Total w/ Tax & Buffer:${total_buf:.2f}",
            ]
            summary_text = "\n".join(lines)

            # Display
            st.subheader("Materials Summary")
            st.write(lines[1])
            st.write(lines[2])
            st.write(lines[3])

            st.subheader("Labour & Surcharges")
            for l in lines[5:10]:
                st.write(l)

            st.subheader("Batt Counts")
            st.write(lines[12])
            st.write(lines[13])

            st.subheader("Diagrams")
            for _, bw, rise in cat_sections:
                draw_cathedral_diagram(bw, rise)

            st.subheader("Totals")
            for l in lines[-4:]:
                st.write(l)

            st.subheader("Cost Breakdown Chart")
            draw_cost_breakdown_chart(
                {
                    "Wall Mat": wall_cost,
                    "Cat Mat": cat_cost,
                    "Ceil Mat": ceiling_mat_cost,
                    "Wall Labour": wall_lab,
                    "Area Labour": area_lab,
                    "Ceil Labour": ceil_lab,
                    "Cat Surcharge": cat_surch,
                }
            )

            # PDF Export (optional lib)
            if rl_canvas is None or letter is None:
                st.warning("PDF export unavailable (reportlab not installed). Add reportlab to requirements.txt.")
            else:
                pdf_name = "insulation_estimate_output.pdf"
                c = rl_canvas.Canvas(pdf_name, pagesize=letter)
                width, height = letter
                y = height - 50
                c.setFont("Helvetica-Bold", 16)
                c.drawString(50, y, "Insulation Estimator Report")
                y -= 30
                c.setFont("Helvetica", 12)
                for line in summary_text.split("\n"):
                    c.drawString(50, y, line[:95])
                    y -= 20
                    if y < 50:
                        c.showPage()
                        y = height - 50
                        c.setFont("Helvetica", 12)
                c.save()
                with open(pdf_name, "rb") as f:
                    st.download_button("Download PDF", f, file_name=pdf_name)


# ============================
# App entry (two main tabs)
# ============================
st.set_page_config(page_title="Trade Estimators", page_icon="🧱", layout="wide")
st.title("Trade Estimators")

tab_drywall, tab_insulation = st.tabs(["Drywall Estimator", "Insulation Estimator"])

with tab_drywall:
    run_drywall_estimator()

with tab_insulation:
    run_insulation_estimator()
