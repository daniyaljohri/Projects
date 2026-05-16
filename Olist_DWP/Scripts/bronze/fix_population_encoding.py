import pandas as pd

df = pd.read_csv(
    r'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\muncipal_population_est.csv',
    dtype=str,
    encoding='utf-8-sig'
)

df.columns = df.columns.str.strip()

df = df.rename(columns={
    'UF':                   'uf',
    'COD. UF':              'cod_uf',
    'COD. MUNIC':           'cod_munic',
    'NOME DO MUNICÍPIO':    'nome_municipio',
    'POPULAÇÃO ESTIMADA':   'populacao_estimada'
})

# Print to confirm fix worked before saving
print(df['nome_municipio'].head(15))

# Save to a brand new filename to avoid any caching issue
df.to_csv(
    r'D:\Projects\Data_Warehouse_Project\Datasets\Enrichment\population_fixed.csv',
    index=False,
    encoding='utf-8-sig'
)

print("Saved to population_fixed.csv")