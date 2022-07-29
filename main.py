import pandas as pd
import meraki
import requests
import bs4 as bs
import config
import sys
import pathlib
from PyQt5 import QtCore, QtWidgets, QtWebEngineWidgets

api_key = config.api_key

# Get table from EoL page
url = 'https://documentation.meraki.com/General_Administration/Other_Topics/Meraki_End-of-Life_(EOL)_Products_and_Dates'
dfs = pd.read_html(url)

# Get Links from table
requested_url = requests.get(url)
soup = bs.BeautifulSoup(requested_url.text, 'html.parser')
table = soup.find('table')

links = []
for row in table.find_all('tr'):
  for td in row.find_all('td'):
    sublinks = []
    if td.find_all('a'):
      for a in td.find_all('a'):
        sublinks.append(str(a))
      links.append(sublinks)

# Add links to dataframe
eol_df = dfs[0]
eol_df['Upgrade Path'] = links

# Pick organizations you want to fetch inventory from
dashboard = meraki.DashboardAPI(api_key)
orgs = dashboard.organizations.getOrganizations()
print("Your API Key has access to the following organizations:")
i = 1
for org in orgs:
  print(f"{i} - {org['name']}")
  i = i+1

choice = input("Type the number of the org or orgs (separated by commas) that you wish to obtain lifecycle information for: ")

int_choice = [int(x)-1 for x in choice.split(',')]
org_map = map(orgs.__getitem__, int_choice)
org_list = list(org_map)

# Create separate lists of inventory for each org
inventory_list = [{f"{x['name']} - {x['id']}": dashboard.organizations.getOrganizationInventoryDevices(x['id'])} for x in org_list]

eol_report_list = []

# Generate a new DataFrame for each Inventory List
for inventory in inventory_list:
  for key in inventory.keys():
    inventory_df = pd.DataFrame(inventory[key])

    # Don't include devices not assigned to any networks, only consider "in use" devices
    inventory_unassigned_df = inventory_df.loc[inventory_df['networkId'].isna()].copy()
    inventory_assigned_df = inventory_df.loc[~inventory_df['networkId'].isna()].copy()

    inventory_assigned_df['lifecycle']=""

    inventory_assigned_df['model'].isin(eol_df['Product']).astype(int)

    # Split SKUs that had joint announcements
    pattern = 'MV21|MX64|MX65|MS220-8|series'
    mask = eol_df['Product'].str.contains(pattern, case=False, na=False)

    new_eol_df = eol_df[mask].copy()

    # Generate entries for specific submodels to count properly
    new_eol_df.replace(to_replace='MX64, MX64W', value = 'MX64W', inplace=True)
    new_eol_df.replace(to_replace='MS220-8', value = 'MS220-8P', inplace=True)
    new_eol_df.replace(to_replace='MX65', value = 'MX65W', inplace=True)
    new_eol_df.replace(to_replace='MV21\xa0& MV71', value = 'MV71', inplace=True)
    new_eol_df.replace('MV21*', 'MV71', regex=True, inplace=True)

    # Split up MS220 and MS320 switches in their specific submodels for proper counting
    ms220_mask = new_eol_df['Product'].str.contains('MS220\xa0series', case=False, na=False)
    ms320_mask = new_eol_df['Product'].str.contains('MS320\xa0series', case=False, na=False)
    ms220_24_row = new_eol_df[ms220_mask].copy()
    ms220_24_row["Product"]="MS220-24"
    ms220_24p_row = new_eol_df[ms220_mask].copy()
    ms220_24p_row["Product"]="MS220-24P"
    ms220_48_row = new_eol_df[ms220_mask].copy()
    ms220_48_row["Product"]="MS220-48"
    ms220_48lp_row = new_eol_df[ms220_mask].copy()
    ms220_48lp_row["Product"]="MS220-48LP"
    ms220_48fp_row = new_eol_df[ms220_mask].copy()
    ms220_48fp_row["Product"]="MS220-48FP"
    ms320_24_row = new_eol_df[ms320_mask].copy()
    ms320_24_row["Product"]="MS320-24"
    ms320_24p_row = new_eol_df[ms320_mask].copy()
    ms320_24p_row["Product"]="MS320-24P"
    ms320_48_row = new_eol_df[ms320_mask].copy()
    ms320_48_row["Product"]="MS320-48"
    ms320_48lp_row = new_eol_df[ms320_mask].copy()
    ms320_48lp_row["Product"]="MS320-48LP"
    ms320_48fp_row = new_eol_df[ms320_mask].copy()
    ms320_48fp_row["Product"]="MS320-48FP"

    # Concatenate everything
    new_eol_df = pd.concat([new_eol_df,ms220_24_row,ms220_24p_row,ms220_48_row,ms220_48lp_row,ms220_48fp_row,ms320_24_row,ms320_24p_row,ms320_48_row,ms320_48lp_row,ms320_48fp_row])
    new_eol_df = new_eol_df[new_eol_df["Product"].str.contains("series")==False]
    final_eol_df = pd.DataFrame()
    final_eol_df = pd.concat([eol_df, new_eol_df])
    final_eol_df.replace(to_replace='MV21\xa0& MV71', value = 'MV21', inplace=True)

    final_eol_df['Total Units']=final_eol_df['Product'].map(inventory_assigned_df['model'].value_counts())
    eol_report = final_eol_df.dropna()
    eol_report = eol_report.sort_values(by=["Total Units"], ascending=False)

    # Drop index column
    eol_report = eol_report.reset_index(drop=True)

    # Construct dict of each of the reports
    eol_report_dict = {"name": key,
                       "report": eol_report}

    eol_report_list.append(eol_report_dict)

# Define html document variables
page_title_text='Cisco Meraki Lifecycle Report'
title_text = 'Cisco Meraki Lifecycle Report'
text = '''
This report lists all of your equipment currently in use that has an end of life announcement. They are ordered by the
total units column, and the Upgrade Path column links you to the EoS announcement with recommendations on upgrade paths.
'''
org_text = eol_report_list[0]['name']


# Create header and formatting
html = f'''
    <html>
        <style>
        body {{font-family: Inter, Arial, sans-serif; margin: 15px;}}
        h {{font-family: Inter, Arial, sans-serif; margin: 15px;}}
        h2 {{font-family: Inter, Arial, sans-serif; margin: 15px;}}
        table {{border-collapse: collapse; margin: 15px;}}
        th {{text-align: left; background-color: #04AA6D; color:white; padding: 8px;}}
        td {{padding: 8px;}}
        tr:nth-child(even) {{background-color: #dedcdc;}}
        tr:hover {{background-color: 04AA6D;}}
        p {{margin: 15px;}}
        </style>
        <head>
            <img src='cisco-meraki-logo.png' width="700">
            <title>{page_title_text}</title>
        </head>
        <body>
            <h1>{title_text}</h1>
            <p>{text}</p>
    '''

# For each EOL Report, add a section to the HTML document
for i in range(len(eol_report_list)):
  add_html = f'''
            <h2>{eol_report_list[i]['name']}</h2>
            {eol_report_list[i]['report'].to_html(render_links=True, escape=False, index=False)}
            '''
  html = html+add_html

# Close HTML document and render
close_html = f'''
        </body>
    </html>
    '''
html = html+close_html
# 3. Write the html string as an HTML file
with open('html_report.html', 'w') as f:
    f.write(html)

# Function to export HTML document as PDF
def html_to_pdf(html, pdf):
  app = QtWidgets.QApplication(sys.argv)

  page = QtWebEngineWidgets.QWebEnginePage()

  def handle_print_finished(filename, status):
    print("finished", filename, status)
    QtWidgets.QApplication.quit()

  def handle_load_finished(status):
    if status:
      page.printToPdf(pdf)
    else:
      print("Failed")
      QtWidgets.QApplication.quit()

  page.pdfPrintingFinished.connect(handle_print_finished)
  page.loadFinished.connect(handle_load_finished)
  page.load(QtCore.QUrl.fromLocalFile(html))
  app.exec_()

# Export HTML as PDF
CURRENT_DIR = str(pathlib.Path().absolute())
filename = CURRENT_DIR+"/html_report.html"
print(filename)

html_to_pdf(filename, "Lifecycle Report.pdf")
