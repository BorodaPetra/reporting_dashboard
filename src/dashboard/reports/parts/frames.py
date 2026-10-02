"""Legacy helpers of the parts report: stock age, demand age, extended stock.

Each report took the functions it needs and was reconciled with the old
results; the other functions of this module were deleted in D6.
"""

import numpy as np
import pandas as pd


def fill_empty_data(df):
    filled_df = df.copy()
    str_cols  = (df.select_dtypes(['object', 'str'])).columns
    num_cols  = (df.select_dtypes('number')).columns
    cat_cols  = (df.select_dtypes('category')).columns 
    date_cols = (df.select_dtypes('datetime')).columns
    filled_df[cat_cols] = filled_df[cat_cols].astype(str)
    filled_df[str_cols] = filled_df[str_cols].fillna('-')
    filled_df[num_cols] = filled_df[num_cols].fillna(0)
    filled_df[date_cols] = filled_df[date_cols].fillna('-')
    filled_df = filled_df.fillna('-')
    return filled_df


def get_extended_stock(stock_data, basic_data, demand_data):
    inventory_data = stock_data.inventory.copy()
    #inventory_data = extract_time_groups(inventory_data, ["DATE"])
    inventory_data = inventory_data.groupby(['DATE','PTS_NO'],as_index=False)[['AVAILABLE','INCOMING','ORDERED']].last()
    inventory_data['DATE_YM'] = inventory_data['DATE'].dt.strftime('%Y-M%m')
    inventory_data = inventory_data.merge(basic_data.partsmaster[
            ["PTS_NO","DESCR","STOP_FLAG","WEIGHT","PNL","CAT","PCLASS","MDLS","VND_NAME","COO","HID"]
        ],
        on=["PTS_NO"],
        how="left",
    )
    
    for col in ['PCLASS','CAT','VND_NAME','HID','PNL','STOP_FLAG']:
        if col == 'PNL':
            inventory_data[col] = inventory_data[col].fillna(inventory_data["PTS_NO"])
        elif col == 'STOP_FLAG':
            inventory_data[col] = inventory_data[col].fillna('N')
        else:
            inventory_data[col] = inventory_data[col].fillna('-')
    
    inventory_data = (inventory_data.merge(
                    demand_data.m
                    .T.rolling(12)
                    .mean().T
                    .round(2)
                    .dropna(axis=1)
                    .T
                    .stack(future_stack=True).dropna()
                    .reset_index()
                    .set_axis(["PNL","DATE_YM","AMC"],axis=1),
                    on=["DATE_YM", "PNL"],
                    how="left",
                    )
                )   
    inventory_data['RANK'] = (inventory_data.set_index(['DATE_YM','PNL']).index
                        .map(demand_data.rank_table.T.stack(future_stack=True).dropna()).fillna('F')
                        )
    inventory_data["AMC"] = inventory_data["AMC"].fillna(0)
    inventory_data["MOH"] = (inventory_data["AVAILABLE"] / inventory_data["AMC"]).round(1).replace({np.inf: 999})
    inventory_data["MOH_GRP"] = pd.cut(
        inventory_data["MOH"],
        (-1, 0, 1, 6, 12, 24, 999),
        precision=1,
        labels=("0", "0-1", "1-6", "6-12", "12-24", "24++"),
    )

    inventory_data['SAGE'] = inventory_data.set_index(['DATE','PTS_NO']).index.map(stock_data.age.T.stack(future_stack=True).dropna()).fillna(-1)
    #inventory_data['SAGE_LAST']  = inventory_data.set_index(['DATE','PTS_NO']).index.map(stock_data.arrival.T.stack())
    #inventory_data['SAGE']       = inventory_data['SAGE_LAST'].fillna(inventory_data['SAGE_FIRST'])
    #inventory_data['SAGE_LAST']  = inventory_data['SAGE_LAST'].fillna(-1)
    inventory_data['DAGE'] = inventory_data.set_index(['DATE','PNL']).index.map(demand_data.age.T.stack(future_stack=True).dropna()).fillna(999)
    
    inventory_data["SAGE_GRP"] = pd.cut(
        inventory_data["SAGE"],
        (-999, -1, 1, 2, 3, 4, 999),
        precision=1,
        labels=("TBD", "0-1", "1-2", "2-3", "3-4", "4++"),
    )
        
    inventory_data["DAGE_GRP"] = pd.cut(
        inventory_data["DAGE"],
        (-999, -1, 1, 2, 3, 4, 999),
        precision=1,
        labels=("TBD", "0-1", "1-2", "2-3", "3-4", "4++"),
    )
    
    
    # inventory_data['DS_SAGE_FIRST']   = [1 if (ts > 2 and td > 3 and p in ["M", "OTHER"]) else\
    #                                1 if (ts > 2 and td > 2 and p in ["CM", "C", "W"])\
    #                                    else 0 for ts,td,p in zip(inventory_data['SAGE_FIRST'],inventory_data['DAGE'],inventory_data['PCLASS'])]
    # PERF: DEAD / ZOMBIE / SAGE / DAGE below: np.select / np.where over the columns instead of
    # Python list comprehensions, one interpreter step per row
    inventory_data['DEAD']   = [1 if (ts > 2 and td > 3 and p in ["M", "OTHER"]) else\
                                1 if (ts > 2 and td > 2 and p in ["CM", "C", "W"])\
                                   else 0 for ts,td,p in zip(inventory_data['SAGE'], inventory_data['DAGE'], inventory_data['PCLASS'])]
    inventory_data["ZOMBIE"] = [
        1 if (stop == 1 and dead == 0) else 0
        for stop, dead in zip(inventory_data["STOP_FLAG"], inventory_data["DEAD"])
    ]
    
    inventory_data['SAGE'] = [s if a>0 else 0 for s,a in zip(inventory_data.SAGE,inventory_data.AVAILABLE)]
    inventory_data['DAGE'] = [d if a>0 else 0 for d,a in zip(inventory_data.DAGE,inventory_data.AVAILABLE)]
    inventory_data["SAGE_GRP"] =  [sg if s>0 else 'TBD' for s,sg in zip(inventory_data.SAGE,inventory_data.SAGE_GRP)]
    inventory_data["DAGE_GRP"] =  [dg if d>0 else 'TBD' for d,dg in zip(inventory_data.DAGE,inventory_data.DAGE_GRP)]
 
    
    return inventory_data


def get_stock_age(initial_stock_age, available_stock_table):
    initial_age = initial_stock_age.groupby('PTS_NO')['DAYS'].max()
    final_stock_age = available_stock_table.copy()
    if final_stock_age.columns[0]  <= pd.Timestamp('2022-09-30'):
        final_stock_age[final_stock_age.columns[0]] = initial_age
    else:
        final_stock_age[final_stock_age.columns[0]] = initial_age.apply(lambda x: 0.2 + x + (final_stock_age.columns[0] - pd.Timestamp('2022-09-30')).days)
    # PERF: apply(axis=1) calls age_calc once per part; a running counter that resets on zeros
    # can be computed for the whole table column by column with numpy
    return final_stock_age.apply(lambda x: age_calc(x),axis=1)


def age_calc(row):
    values_list = []
    c = row.iloc[0]
    #days = row.index.diff()
    freq_days = 31 #days.days[-1]
    #freq_label = 'W' if freq_days == 7 else 'M' if freq_days in list(range(29,33)) else 'Q' if freq_days in [n*3 for n in list(range(29,33))] else None
    #freq_devider = {'W':7,'M':30,'Q':90}
    # PERF: row[:d+1].sum() - row[:d].sum() is row.iloc[d]: comparing the value itself is O(n), not O(n^2)
    for digit in range(len(row)):
        if row[:digit+1].sum() > row[:digit].sum():
            c += round(1*freq_days,2)
        elif row[:digit+1].sum() == row[:digit].sum():
            c = 0
        values_list.append(round(c/30/12,2))
    return pd.Series(values_list, index=row.index).replace({0:np.nan})


def last_time_on_stock(stock_avl_table):
    last_time_on_stock = {}
    stock_avl_table = stock_avl_table.copy().T.replace({0:np.nan})
    # PERF: m = table.notna(); m[::-1].idxmax() where m.any() gives every last index at once
    for col in stock_avl_table.columns:
        last_time_on_stock[col] = stock_avl_table[col].last_valid_index()
    # to_datetime: when no part was ever on stock the values are all None (object), .dt failed
    return pd.to_datetime(pd.Series(last_time_on_stock)).dt.strftime('%Y-%m-%d').fillna('-')


# PERF: filters the frame once per month; one pass is max SO_DATE per (PNL, month end),
# ffill along the months, then month end minus that date
def get_demand_age(daily_subset):
    return (
        pd.concat(
            [
                daily_subset[daily_subset["SO_DATE"] <= x]
                .sort_values("SO_DATE", ascending=False)
                .groupby("PNL",as_index=False)["SO_DATE"]
                .max().assign(diff = lambda d: (x - d['SO_DATE']).dt.days/30/12)[['PNL','diff']].set_index('PNL')
                for x in list(pd.date_range('2022-09-30',pd.Timestamp('today')+pd.offsets.MonthEnd(),freq='ME'))
            ],
            axis=1,
        )
       .set_axis(list(pd.date_range('2022-09-30',pd.Timestamp('today')+pd.offsets.MonthEnd(),freq='ME')), axis=1)
        )


def filter_latest(frame):
    return frame[frame['DATE']>=frame['DATE'].max()]
