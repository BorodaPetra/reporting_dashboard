"""Delivery status of the containers in the tracing file (legacy helper, reconciled in D4)."""

import numpy as np
import pandas as pd


def prepare_delivery_status_frame(daily, *files):
    tmp_concat = pd.concat(files, axis=0) if len(files) > 1 else files[0]
    tmp_concat.columns = [
        "CONT_TYPE",
        "CONT_NUM",
        "DELIVERY_TYPE",
        "INVOICE",
        "POD",
        "POA",
        "ETD",
        "ETA",
        "UPD_ETA",
        "COMMENTS",
    ]
    tmp_concat["CONT_TYPE"] = tmp_concat["CONT_TYPE"].str.upper()
    tmp_concat["POD"] = tmp_concat["POD"].astype(str).apply(lambda x: x.capitalize())
    tmp_concat["POA"] = tmp_concat["POA"].astype(str).apply(lambda x: x.capitalize())
    tmp_concat["TODAY"] = pd.to_datetime("today").normalize()
    tmp_concat["VND_NAME"] = (
        tmp_concat["INVOICE"]
        .map(daily.groupby("PO_INVOICE")["VND_NAME"].last())
    )
    tmp_concat["AMOUNT"] = tmp_concat["INVOICE"].map(
        daily.groupby("PO_INVOICE")["PA_USD"].sum()
    )

    # tmp_concat['ETA'] = [x + np.timedelta64(5,'D') if x>=t else x for x,t in zip(tmp_concat['ETA'],tmp_concat['TODAY'])]
    tmp_concat["UPD_ETA"] = np.where(
        tmp_concat["UPD_ETA"].isna(), tmp_concat["ETA"], tmp_concat["UPD_ETA"]
    )
    tmp_concat["ETD_DAYS"] = (tmp_concat["ETA"] - tmp_concat["ETD"]).dt.days
    tmp_concat["UPD_ETD_DAYS"] = (tmp_concat["UPD_ETA"] - tmp_concat["ETD"]).dt.days
    tmp_concat["ATD_DAYS"] = (tmp_concat["TODAY"] - tmp_concat["ETD"]).dt.days
    # PERF: UPD_ETD_DAYS.clip(upper=ATD_DAYS) is this min (NaN handled the same way), and
    # .str.capitalize() replaces the apply(lambda) on POD / POA above
    tmp_concat["ATD_DAYS"] = [
        y if x > y else x
        for x, y in zip(tmp_concat["UPD_ETD_DAYS"], tmp_concat["ATD_DAYS"])
    ]
    tmp_concat["LEFT_DAYS"] = tmp_concat["UPD_ETD_DAYS"] - tmp_concat["ATD_DAYS"]
    tmp_concat["COMPLITION"] = tmp_concat["ATD_DAYS"] / tmp_concat["UPD_ETD_DAYS"]

    tmp_concat["DELAY"] = tmp_concat["UPD_ETD_DAYS"] - tmp_concat["ETD_DAYS"]
    # tmp_concat = tmp_concat.drop(columns=['INVOICE'])
    # tmp_concat['COMMENTS'] = ['-' if y == 'UNICO' else x for x,y in zip(tmp_concat['COMMENTS'],tmp_concat['CARRIER'])]
    tmp_concat["CONT_NUM"] = [
        f"{x} ({y})" for x, y in zip(tmp_concat.CONT_NUM, tmp_concat.POD)
    ]
    tmp_concat["PIC"] = tmp_concat["DELIVERY_TYPE"].map(
        {"AIR": "✈️", "RAIL": "🚂", "SEA_RAIL": "🚢"}
    )
    tmp_concat["PIC"] = [
        "🚂" if (c > 0.5 and t == "SEA_RAIL") else x
        for x, c, t in zip(
            tmp_concat["PIC"], tmp_concat["COMPLITION"], tmp_concat["DELIVERY_TYPE"]
        )
    ]

    # tmp_concat['CONT_TYPE'] = tmp_concat.apply(lambda x: '40' if  (str(x['CONT_TYPE'])!='np.nan' and x['DELIVERY_TYPE']=='RAIL') else x['CONT_TYPE'], axis=1)
    max_days = int(tmp_concat["ETD_DAYS"].max())
    tmp_concat["xaxis"] = np.where(
        tmp_concat["UPD_ETA"].notna(),
        tmp_concat["UPD_ETA"] + np.timedelta64(max_days, "D"),
        tmp_concat["ETA"] + np.timedelta64(max_days, "D"),
    )
    tmp_concat["DELAY_TEXT"] = [
        f"+{int(x)}" if str(x) != "nan" else x for x in tmp_concat["DELAY"]
    ]

    return tmp_concat
