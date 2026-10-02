from flask import current_app

from dashboard.data import legacy


def report_groups(report: str | None = None) -> list[str]:
    """Groups of a report; <REPORT>_EXCLUDE_GROUPS removes some of them."""
    exclude = (
        set(current_app.config.get(f"{report.upper()}_EXCLUDE_GROUPS", []))
        if report
        else set()
    )
    return [group for group in legacy.dealer_groups() if group not in exclude]


def breakdown_group() -> str:
    """The group of the monthly breakdown chart and mailing (BREAKDOWN_GROUP)."""
    groups = report_groups()
    configured = current_app.config.get("BREAKDOWN_GROUP")
    return configured if configured in groups else groups[0]


def breakdown_subgroups() -> dict[str, list[str]]:
    """Sub-groups of the breakdown chart: label -> dealer codes
    (BREAKDOWN_SUBGROUPS="Label A:code1|code2,Label B:code3")."""
    return {
        label: codes.split("|")
        for label, codes in current_app.config.get("BREAKDOWN_SUBGROUPS", {}).items()
    }


def warehouse_labels() -> dict[str, str]:
    """Dealer code -> label of a warehouse that is not a stock location of HCMR."""
    return dict(current_app.config.get("DEALER_WAREHOUSE_LABELS", {}))


def mining_suppliers() -> list[str]:
    """Suppliers whose parts are mining parts whatever their HID (MINING_SUPPLIERS)."""
    return list(current_app.config.get("MINING_SUPPLIERS", []))


def with_mining_suppliers(parts, supplier_column: str = "VND_NAME"):
    """The old partsmaster rule: PCLASS "M" for the parts of MINING_SUPPLIERS,
    except parts that fit both kinds of machines ("CM" wins, as before)."""
    parts = parts.copy()
    mask = parts[supplier_column].isin(mining_suppliers()) & (parts["PCLASS"] != "CM")
    parts.loc[mask, "PCLASS"] = "M"
    return parts


def demand_groups() -> list[str]:
    """Dealer groups whose orders make the demand of the parts model: every dealer of the
    report groups. The old sales report did the same (DLR_META);
    the old parts report used a fixed list of codes, umap.dealer_codes_for_use."""
    return report_groups()
