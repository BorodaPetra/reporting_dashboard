"""Legacy helpers shared by several reports: time groups of the daily frame, prices.

Each report took the functions it needs and was reconciled with the old
results; the other functions of this module were deleted in D6.
"""

import numpy as np
import pandas as pd


def extract_time_groups(df, target_cols, pre_convert=True):
    df = df.copy()
    df[target_cols] = (
        df[target_cols]
        if not pre_convert
        else df[target_cols].apply(pd.to_datetime, errors="coerce")
    )
    for col in target_cols:
        try:
            df[f"{col}_Y"] = df[col].dt.strftime("%Y")
            df[f"{col}_FY"] = (df[col].dt.to_period("Q-MAR").dt.qyear - 1).astype(str)
            df[f"{col}_YW"] = df[col].dt.strftime("%Y-W%W")
            df[f"{col}_YM"] = df[col].dt.strftime("%Y-M%m")
        except Exception as e:
            print(e)
            continue
    return df


def handle_prices(data_src, price_src):
    
    idx = pd.date_range('2022-04-30', pd.Timestamp('today') + pd.offsets.MonthEnd(1), freq='ME') 
    
    if hasattr(data_src, "avg_pp"):
        data_src.avg_pp.reset_index(inplace=True)
        data_src.avg_pp["DATE"] = data_src.avg_pp["DATE"] + pd.offsets.MonthBegin()
        data_src.avg_pp = data_src.avg_pp.groupby(["DATE", "PTS_NO"]).agg(
            {"AVG_PP": "max"}
        )  # avg_pp[['DATE','PTS_NO','AVG_PP']]
        price_src.avg_pp = data_src.avg_pp.reset_index().assign(
            DATE_YM=lambda x: x["DATE"].dt.strftime("%Y-M%m")
        )
        del data_src.avg_pp

    if hasattr(data_src,'cost_rub'):
        rub_group = data_src.cost_rub.groupby(['PTS_NO','DATE'])['COST_RUB'].max()
        cost = (rub_group
                                .unstack('PTS_NO')
                                .resample('ME').max()
                                .reindex(idx)
                                .T.replace({0:np.nan})
                                .ffill(axis=1, limit=2)
                                .bfill(axis=1, limit=1)
                                .stack(future_stack=True).dropna()
                                .reset_index()
                                .set_axis(['PTS_NO','DATE','COST_RUB'],axis=1)
                                .assign(DATE_YM=lambda x:x['DATE'].dt.strftime('%Y-M%m'))
               )
 
        avg_usd_rate = data_src.usd_rate.assign(DATE_YM=lambda x:x['DATE'].dt.strftime('%Y-M%m')).groupby('DATE_YM')['CURRENCY_RATE'].mean().round(4)   
        cost['USD_RATE'] = cost['DATE_YM'].map(avg_usd_rate)
        cost['COST_USD'] = cost['COST_RUB'] / cost['USD_RATE']
        price_src.cost_usd = cost[['PTS_NO','DATE','DATE_YM','COST_USD']].copy()
        price_src.cost_rub = cost[['PTS_NO','DATE','DATE_YM','COST_RUB']].copy()
        price_src.cost = cost
        del data_src.cost_rub
    
    if hasattr(data_src, "purchase_price"):
        price_src.pp_usd = (
            data_src.purchase_price.groupby(["DATE", "PTS_NO"])
            .agg({"PRICE": "max"})
            .unstack("PTS_NO")
            .resample("ME")
            .max()
            .reindex(idx)
            .T.replace({0: np.nan})
            .ffill(axis=1)
            .stack(future_stack=True).dropna()
            .droplevel(level=0, axis=0)
            .reset_index()
            .set_axis(["PTS_NO", "DATE", "PP_USD"], axis=1)
            .assign(DATE_YM=lambda x: x["DATE"].dt.strftime("%Y-M%m"))
        )
        del data_src.purchase_price
    
    if hasattr(data_src,'partsmaster'):
         price_src.lp_usd = data_src.partsmaster.groupby('PTS_NO',as_index=False)['DLP'].max().assign(DATE = pd.to_datetime('today').normalize()).assign(DATE_YM=lambda x: x["DATE"].dt.strftime("%Y-M%m"))
    
    if hasattr(data_src,'daily'):
        price_src.shipped_pp_usd = (data_src.daily[data_src.daily['SO_NUM'].isna()]
                                    .groupby([pd.Grouper(key='SHIP_DATE',freq='ME'),'PTS_NO'])['PP_USD']
                                    .max()
                                    .unstack('PTS_NO')
                                    .reindex(idx)
                                    .T.replace({0: np.nan})
                                    .bfill(axis=1)
                                    .ffill(axis=1)
                                    .stack(future_stack=True).dropna()
                                    .reset_index()
                                    .set_axis(["PTS_NO", "DATE", "SHIPPED_PP_USD"], axis=1)
                                    .assign(DATE_YM=lambda x: x["DATE"].dt.strftime("%Y-M%m")))

    return price_src
