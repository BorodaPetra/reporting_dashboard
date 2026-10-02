"""Presentation of the parts report: the old uframe_new.prettify_outupt (D4.3).

Copied unchanged (table and cards: the page's JavaScript depends on the column
names), except the monthly breakdown. The old function returned one 'details'
table built for the first part only and failed with several parts; now each tab
(demand, stock, prices) gets one table per part: a row per month, newest first
(D4.3).
"""

import math

import numpy as np
import pandas as pd

from dashboard.reports.parts.frames import fill_empty_data

SHOW_MONTHS = 24                     # months in the tables of the demand / stock / prices tabs


def _cell(value):
    """JSON-friendly cell: '-' for no value, whole numbers without '.0'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def monthly_tables(idx: pd.Index, months, frames: dict[str, pd.DataFrame]) -> dict:
    """{part: {"columns": ["Month", *frames], "rows": [[month, value, ...], ...]}} for the
    last SHOW_MONTHS months, newest first. frames: column title -> parts x month labels."""
    months = sorted(set(months))[-SHOW_MONTHS:][::-1]
    wide = {title: frame.reindex(index=idx, columns=months) for title, frame in frames.items()}
    # PERF: one .at lookup per cell (parts x months x columns, <= 500 x 24 x 5). Fine for the page;
    # for larger lists stack the frames into one long frame (part, month) -> columns and split it by part.
    tables = {}
    for part in idx:
        rows = [[month] + [_cell(wide[title].at[part, month]) for title in frames] for month in months]
        tables[part] = {"columns": ["Month", *frames], "rows": rows}
    return tables


def month_labels(frame: pd.DataFrame, column: str = "DATE") -> pd.DataFrame:
    return frame.assign(DATE_YM=pd.to_datetime(frame[column]).dt.strftime("%Y-M%m"))


def prettify_output(idx,
                    partsmaster_data,
                    price_data,
                    demand_data,
                    stock_data,
                    currency_data,
                    report_url=None):
    
    partsmaster_data = (partsmaster_data[~partsmaster_data['PTS_NO'].duplicated(keep='last')]
                          .copy()
                          .set_index('PTS_NO')
                          .reindex(idx)
                          .rename({'PTS_NO'   : 'Part',
                                    'JV'      : 'JV Code',
                                    'DESCR'   : 'Description',
                                    'VND_CODE': 'Vendor Code',
                                    'WEIGHT'  : 'Weight Net (kg)',
                                    'PROHIBITION_CODE' : 'Prohibited',
                                    'COO'     : 'Origin',
                                    'QPM'     : 'Set (per machine)',
                                    'HID'     : 'HID',
                                    'HID_FULL': 'HID Descr.',
                                    'MDLS'    : 'Models',
                                    'MDLS_ALL': 'all models',
                                    'TNVED'   : 'TNVED',
                                    'PNL'     : 'Latest',
                                    'PREV'    : 'Previous',
                                    'CAT'     : 'Description Cat.',
                                    'VND_NAME': 'Vendor',
                                    'PCLASS'  : 'Type',
                                    'STOP_FLAG':'StopFlag'},
                                  axis='columns')
                        )
    models_data = partsmaster_data[['Models']].copy()
    pmm = (partsmaster_data
           .rename_axis('PTS_NO', axis=0)
           .reset_index()
           .groupby('Latest')['PTS_NO'].unique()
           .explode()
           )
    
    recent_prices = (price_data.recent_prices
                        .copy()
                        .set_index('PTS_NO')
                        .reindex(idx, fill_value=0)
                        .rename({'COST_RUB'      : 'Cost (RUB)',
                                 'COST_USD'      : 'Cost (USD)',
                                 'DNP_CPD_USD'   : 'CPD Net Price (USD)',
                                 'BUY_RATE'      : 'HCMR Buy Rate',
                                 'PP_USD'        : 'Purch. Price (USD)',
                                 'DLP'           : 'Sales List Price (USD)',
                                 'SHIPPED_PP_USD': 'Purch. Avg (USD)'},
                            axis='columns')
                   )
 
    demand_stats = (demand_data.stats[['sum_12','sum_24', 'sum', 'avg_12', 'wavg','dmd_once','MC',
                                'rank_most','rank_end','SS_wavg','ROP_wavg','SMAX_wavg',
                                'stock_flag','SL','LT','LTD_wavg','dmd_recency']]
                        .copy()
                    )
    
    demand_stats = (demand_stats[demand_stats.index.isin(partsmaster_data['Latest'])]
                        .copy()
                        .join(pmm)
                        .reset_index(drop=True)
                        .set_index('PTS_NO')
                        .reindex(idx)
                        .rename({'sum_12'    :'Demand (prev. 12M)',
                                    'sum_24'    :'Demand (prev. 24M)',
                                    'sum'       :'Demand (all time)',
                                    'avg_12'    :'Demand Average (12M)',
                                    'wavg'      :'Demand Average (weighted)',
                                    'dmd_once'  :'One time event',
                                    'MC'        :'Main Consumer',
                                    'rank_most' :'Rank (overall)',
                                    'rank_end'  :'Rank (current)',
                                    'dmd_recency':'Demand Recency (M)',
                                    'SS_wavg'   :'Stock Level (Safety)',
                                    'ROP_wavg'  :'Stock Level (Re-order)',
                                    'SMAX_wavg' :'Stock Level (Max)',
                                    'stock_flag':'Stocking Flag',
                                    'LTD_wavg'  :'Level (LTD)',
                                    'LT'        :'Order LT (M)',
                                    'SL'        :'Target Service Rate'
                                },axis=1)
                            .round(2)
                            .fillna({'Rank (overall)':'F','Rank (current)':'F','MC':'-'})
                            .fillna(0)
                )
    
    current_stock_data = (stock_data.current[
                            ['PTS_NO','AVAILABLE', 'INCOMING','ORDERED',
                            'SAGE', 'SAGE_GRP','DAGE','DAGE_GRP',
                            'DEAD','ZOMBIE','STOP_FLAG']]
                            .copy()
                            .set_index('PTS_NO')
                            .reindex(idx)
                            .fillna({'STOP_FLAG':'N','SAGE_GRP':'-','DAGE_GRP':'-'})
                            .fillna(0)
                            .rename({'AVAILABLE' : 'Available (1.Now)',
                                        'INCOMING'  : 'Available (2.Incoming)',
                                        'ORDERED'   : 'Available (3.Ordered)',
                                        'MOH'       : 'Stock MOH (M)',
                                        'MOH_GRP'   : 'Stock MOH (Gr)',
                                        'SAGE'      : 'Stock Age (Y)',
                                        'SAGE_GRP'  : 'Stock Age (Gr)',
                                        'DAGE'      : 'Demand Age (Y)',
                                        'DAGE_GRP'  : 'Demand Age (Gr)',
                                        'DEAD'      : 'Health (Dead)',
                                        'ZOMBIE'    : 'Health (Zombie)',
                                        'STOP_FLAG' : 'StopProc'
                                        },
                                axis='columns')
                            .round({'Demand Age (Y)':1,'Stock Age (Y)':1})
                        )
    
    current_stock_data[['Health (Dead)','Health (Zombie)']] = current_stock_data[['Health (Dead)','Health (Zombie)']].replace({1:'Y',0:'N'}).fillna('N')
    current_stock_data['Available (4.Total)'] = current_stock_data[['Available (1.Now)','Available (2.Incoming)','Available (3.Ordered)']].sum(axis=1)
    current_stock_data['Last Time Available'] = stock_data.last_time_avl
    current_stock_data['Last Time Available'] = current_stock_data['Last Time Available'].fillna("-")
    
    stock_levels = demand_stats[['Stock Level (Safety)','Stock Level (Re-order)','Stock Level (Max)',
                                'Stocking Flag','Order LT (M)','Level (LTD)','Target Service Rate']].copy().fillna(0)
    
    stock_levels = stock_levels.round({'Stock Level (Safety)':0,
                                       'Stock Level (Re-order)':0,
                                       'Stock Level (Max)':0,
                                       'Level (LTD)':0})
    stock_levels['Rec. order'] = [smax - ta if smax-ta>0 else 0 for smax,ta in zip(stock_levels['Stock Level (Max)'],
                                                                                   current_stock_data['Available (4.Total)'],
                                                                                   )]#stock_levels.apply(lambda x: max(x['Stock Level (Max)']-x['Overall stock'],0),axis=1) 
    stock_levels['Target Service Rate'] = stock_levels['Target Service Rate'].apply(lambda x: f'{(x*100)}%')
    stock_levels['Stock Level MOH (Max)'] = [round(avl/dmd,1) if (dmd>0 and avl>0) else '-' for avl,dmd in zip(stock_levels['Stock Level (Max)'],
                                                                                                               demand_stats['Demand Average (weighted)'])]
    recent_prices['Cost (USD)'] = [c if a > 0 else 0 for c,a in zip(recent_prices['Cost (USD)'],current_stock_data['Available (1.Now)'])]
    recent_prices['Cost (RUB)'] = [c if a > 0 else 0 for c,a in zip(recent_prices['Cost (RUB)'],current_stock_data['Available (1.Now)'])]
    
    stock_avl_details = stock_data.avl.copy().reindex(idx, fill_value=0)
    stock_avl_details.columns = stock_avl_details.columns.strftime('%Y-M%m')
    stock_age_details = stock_data.age.copy().reindex(idx, fill_value=0).round(2)
    stock_age_details.columns = stock_age_details.columns.strftime('%Y-M%m')
    demand_qty_details = (demand_data.m[demand_data.m.index.isin(partsmaster_data['Latest'])].copy()
                            .join(pmm)
                            .reset_index(drop=True)
                            .set_index('PTS_NO')
                            .reindex(idx, fill_value=0)
                        )
    demand_age = demand_data.age.copy()                # PNL x month end: years since the last order
    if len(demand_age):
        # labels before the join: with the PTS_NO column the columns stop being a DatetimeIndex
        demand_age.columns = pd.DatetimeIndex(demand_age.columns).strftime('%Y-M%m')
        demand_age_details = (demand_age[demand_age.index.isin(partsmaster_data['Latest'])]
                                .join(pmm)
                                .reset_index(drop=True)
                                .set_index('PTS_NO')
                                .reindex(idx)
                                .round(2))
    else:
        demand_age_details = pd.DataFrame(index=idx)
    demand_rank_details = (demand_data.rank_table[demand_data.rank_table.index.isin(partsmaster_data['Latest'])].copy()
                            .join(pmm)
                            .reset_index(drop=True)
                            .set_index('PTS_NO')
                            .reindex(idx, fill_value='F')
                        )

    cost_rub_details = (price_data.cost_rub.round({'COST_RUB': 0})                        
                            .groupby(['PTS_NO','DATE_YM'])['COST_RUB'].max()
                            .unstack('DATE_YM')
                            .reindex(idx, fill_value=0)
                        ).fillna(0)
    cost_usd_details = (price_data.cost_usd.round({'COST_USD': 2})          # old code: round(0), too coarse for USD
                        .groupby(['PTS_NO','DATE_YM'])['COST_USD'].max()
                        .unstack('DATE_YM')
                        .reindex(idx, fill_value=0)
                    ).fillna(0)
    
    usd_rate_details = (currency_data
                            .set_index('DATE')
                            .resample('ME').mean()
                            .assign(DATE_YM=lambda x: x.index.strftime("%Y-M%m"))
                            .reset_index(drop=True)
                            .set_index('DATE_YM')
                        )
    
    recent_prices['USD/RUB rate'] = round(usd_rate_details.iloc[-1].values[0],2)
    
    pm_drop_cols = ['Models','all models','MDLCODE_MC','MDLCODE_ML','MDLCODE_PM','MDL_COUNT','CM_FLAG','CUSTOMS_PRC','Previous','HIDS','DLP']
    demand_stats     = demand_stats    .drop(columns=['Stock Level (Safety)', 'Stock Level (Re-order)', 'Stock Level (Max)','Stocking Flag', 'Order LT (M)', 'Level (LTD)', 'Target Service Rate'])
    partsmaster_data = partsmaster_data.drop(columns=pm_drop_cols)
    
    datatable_data = pd.concat([partsmaster_data,
                                recent_prices,
                                current_stock_data,
                                stock_levels,
                                demand_stats,
                                models_data],
                            # rename_axis(None): the page header of the part column stays "index";
                            # pandas 2 dropped the index name in this concat, pandas 3 keeps "PTS_NO"
                            axis=1).rename_axis(None).reset_index()
    
    
    
    datatable_data  = fill_empty_data(datatable_data).to_dict(orient='split')
    cards_data = {  
                  'pm'  :  fill_empty_data(partsmaster_data)  .to_dict(orient='index'),
                  'prc' :  fill_empty_data(recent_prices)     .to_dict(orient='index'),
                  'stck':  fill_empty_data(current_stock_data).to_dict(orient='index'),
                  'lvls':  fill_empty_data(stock_levels)      .to_dict(orient='index'),
                  'dmd' :  fill_empty_data(demand_stats)      .to_dict(orient='index'),
                  'mdls':  fill_empty_data(models_data)       .to_dict(orient='index'),
                }
    monthly = month_labels(price_data.monthly)
    purchase = {column: (monthly.pivot_table(index='PTS_NO', columns='DATE_YM', values=column, aggfunc='max')
                         if len(monthly) else pd.DataFrame())
                for column in ('PP_USD', 'AVG_PP')}
    rate = usd_rate_details.iloc[:, 0].round(2)
    price_months = set(cost_rub_details.columns) | set(purchase['PP_USD'].columns) | set(purchase['AVG_PP'].columns)
    price_months = {m for m in price_months if m <= pd.Timestamp('today').strftime('%Y-M%m')}
    details_data = {
        'dmd' : monthly_tables(idx, demand_qty_details.columns, {
                    'Demand (pcs)'      : demand_qty_details,
                    'Rank'              : demand_rank_details,
                    'Demand Age (years)': demand_age_details}),
        'stck': monthly_tables(idx, stock_avl_details.columns, {
                    'Available (pcs)'  : stock_avl_details.fillna(0),
                    'Stock Age (years)': stock_age_details}),
        'prc' : monthly_tables(idx, price_months, {
                    'Cost (RUB)'               : cost_rub_details,
                    'Cost (USD)'               : cost_usd_details,
                    'Purch. Price (USD)'       : purchase['PP_USD'].round(2),
                    'Purch. Avg 12M (USD)'     : purchase['AVG_PP'].round(2),
                    'USD/RUB rate'             : pd.DataFrame([rate.to_dict()] * len(idx), index=idx)}),
    }
    # current prices without monthly history, shown above the price table
    for part, table in details_data['prc'].items():
        table['info'] = {'Sales List Price (USD)': _cell(recent_prices.at[part, 'Sales List Price (USD)']),
                         'CPD Net Price (USD)'   : '-',          # no source
                         'HCMR Buy Rate'         : _cell(recent_prices.at[part, 'HCMR Buy Rate'])}

    return datatable_data, cards_data, details_data
