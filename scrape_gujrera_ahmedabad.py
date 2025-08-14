# Real Estate Project Scraper for Gujarat RERA (Ahmedabad)
# Requirements: selenium, pandas, openpyxl
# Usage: python scrape_gujrera_ahmedabad.py

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains

from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import os
import re

# Desired CSV column order
DESIRED_COLUMNS = [
    'Project Name',
    'RERA Reg. No.',
    'Project Address',
    'Taluka',
    'District',
    'State',
    'Project Type',
    'About Property',
    'Project Start Date',
    'Project End Date',
    'Project Land Area',
    'Total Open Area',
    'Total Covered Area',
    'Carpet Area of Units (Range)',
    'Plan Passing Authority',
    'Redevelopment Project',
    'Affordable Housing',
    'Amenities',
    'Unit Type',
    'Block',
    'Total Units',
    'Available Units',
    'Total No. of Towers/Blocks',
    'Promoter Name',
    'Promoter Type',
    'Contact',
    'Email Id',
    'Address',
    'Office Address',
    # Partner columns (cell value will contain: Name, Mobile, Email Id)
    'Partner 1', 'Partner 2', 'Partner 3', 'Partner 4', 'Partner 5',
    'Project Estimated Cost (Rs.)',
    'Percentage Loan Against Project Estimated Cost',
    'Total Quarterly Compliance Required',
    'Total Complied Quarters',
    'Total Quarterly Compliance Defaulted',
    'Total Annual Compliance Required',
    'Total Complied Annual Compliance',
    'Total Annual Compliance Defaulted',
    'Project Status',
    'Website',
    'Approved Date',
]

DISALLOWED_COLUMNS = {
    'Booked Units as on',
    'Un-booked Units as on',
    # Legacy/duplicate partner columns (name-only) to be dropped when present
    'Partner 1 Name', 'Partner 2 Name', 'Partner 3 Name', 'Partner 4 Name', 'Partner 5 Name',
}

def _order_columns(existing_cols, incoming_cols):
    """Return a unified column list where DESIRED_COLUMNS appear first in the given order,
    followed by any additional columns preserving their discovery order."""
    seen = set()
    union = []
    for c in DESIRED_COLUMNS:
        if c in existing_cols or c in incoming_cols:
            if c not in seen:
                union.append(c); seen.add(c)
    for c in list(existing_cols) + [c for c in incoming_cols if c not in existing_cols]:
        if c in DISALLOWED_COLUMNS:
            continue
        if c not in seen:
            union.append(c); seen.add(c)
    return union

# Utility: append rows to CSV without duplicating by RERA Reg. No.
def append_unique_by_regno(df: pd.DataFrame, file_path: str,
                           reg_col: str = 'RERA Reg. No.',
                           alt_cols = ('RERA Reg Number', 'regno', 'Registration No.', 'Registration Number', 'RERA No')):
    try:
        if df is None or df.empty:
            print(f"No data to append to {file_path}.")
            return

        df = df.copy()
        # Drop disallowed columns if present
        drop_cols = [c for c in df.columns if c in DISALLOWED_COLUMNS]
        if drop_cols:
            df = df.drop(columns=drop_cols)
        # If canonical column missing, try to map from alternates
        if reg_col not in df.columns:
            for c in alt_cols:
                if c in df.columns:
                    df[reg_col] = df[c]
                    break

        if reg_col not in df.columns:
            print(f"[WARN] Missing '{reg_col}' column; skipping append to {file_path} to avoid duplicates.")
            return

        # Normalize values for comparison
        df[reg_col] = df[reg_col].astype(str).str.strip().str.upper()

        existing = set()
        existing_cols = None
        file_exists = os.path.exists(file_path)
        if file_exists:
            try:
                # get existing regnos and columns
                existing_header = pd.read_csv(file_path, nrows=0)
                existing_cols = list(existing_header.columns)
                if reg_col in existing_header.columns:
                    existing_only_reg = pd.read_csv(file_path, usecols=[reg_col])
                    existing = set(existing_only_reg[reg_col].astype(str).str.strip().str.upper().tolist())
                else:
                    existing_full = pd.read_csv(file_path)
                    if reg_col in existing_full.columns:
                        existing = set(existing_full[reg_col].astype(str).str.strip().str.upper().tolist())
            except Exception:
                try:
                    existing_full = pd.read_csv(file_path)
                    if reg_col in existing_full.columns:
                        existing = set(existing_full[reg_col].astype(str).str.strip().str.upper().tolist())
                        existing_cols = list(existing_full.columns)
                except Exception:
                    existing = set()

        # Split into new vs duplicates (existing reg nos)
        df_new = df[~df[reg_col].isin(existing)]
        df_dup = df[df[reg_col].isin(existing)]

        # If file exists, optionally UPDATE existing rows for duplicates (upsert)
        if file_exists:
            try:
                existing_full = pd.read_csv(file_path)
            except Exception as e:
                existing_full = None
                print(f"[WARN] Could not load existing CSV for update: {e}")

            if existing_full is not None:
                # If existing file contains disallowed columns, drop them and rewrite
                existing_drop = [c for c in existing_full.columns if c in DISALLOWED_COLUMNS]
                if existing_drop:
                    existing_full = existing_full.drop(columns=existing_drop)
                    existing_full.to_csv(file_path, index=False)
                    print(f"Removed columns {existing_drop} from {file_path}.")
                # Ensure union columns exist and apply DESIRED_COLUMNS-first order
                union_cols = _order_columns(list(existing_full.columns), list(df.columns))
                header_changed = list(existing_full.columns) != union_cols
                existing_full = existing_full.reindex(columns=union_cols)
                df_new = df_new.reindex(columns=union_cols)
                df_dup = df_dup.reindex(columns=union_cols)

                # Build a normalized key for matching
                existing_keys = existing_full[reg_col].astype(str).str.strip().str.upper()
                # Update existing rows with non-empty incoming values
                updated_count = 0
                if not df_dup.empty:
                    for _, r in df_dup.iterrows():
                        key = str(r[reg_col]).strip().upper()
                        mask = (existing_keys == key)
                        if mask.any():
                            idxs = existing_full.index[mask]
                            for idx in idxs:
                                for col in df.columns:
                                    if col == reg_col:
                                        continue
                                    incoming_val = r.get(col, None)
                                    if pd.isna(incoming_val) or str(incoming_val).strip() == '':
                                        continue
                                    # Write if target is NaN or empty string
                                    if col not in existing_full.columns or pd.isna(existing_full.at[idx, col]) or str(existing_full.at[idx, col]).strip() == '':
                                        existing_full.at[idx, col] = incoming_val
                                        updated_count += 1
                # Always rewrite file when header changed, even if no cell values updated
                if header_changed or updated_count:
                    existing_full.to_csv(file_path, index=False)
                    if updated_count:
                        print(f"Updated {updated_count} field(s) for existing rows in {file_path}.")
                    if header_changed:
                        print(f"Updated header to include new columns in {file_path}.")

        # Append truly new rows
        if not df_new.empty:
            if file_exists:
                # Ensure columns align with current file
                try:
                    existing_full = pd.read_csv(file_path)
                    union_cols2 = _order_columns(list(existing_full.columns), list(df_new.columns))
                    if union_cols2 != list(existing_full.columns):
                        existing_full = existing_full.reindex(columns=union_cols2)
                        existing_full.to_csv(file_path, index=False)
                    df_new = df_new.reindex(columns=union_cols2)
                    df_new.to_csv(file_path, mode='a', index=False, header=False)
                except Exception:
                    # Fallback simple append
                    df_new.to_csv(file_path, mode='a', index=False, header=False)
            else:
                # First write
                # Create header per DESIRED_COLUMNS-first order
                first_cols = _order_columns([], list(df_new.columns))
                df_new = df_new.reindex(columns=first_cols)
                df_new.to_csv(file_path, mode='w', index=False, header=True)
            print(f"Appended {len(df_new)} new rows to {file_path} (skipped {len(df) - len(df_new)} duplicates).")
        else:
            print(f"No new rows to append to {file_path} (all duplicates by {reg_col}).")
    except Exception as e:
        print(f"[ERROR] append_unique_by_regno failed for {file_path}: {e}")

# Setup Selenium
options = webdriver.ChromeOptions()
options.add_argument('--start-maximized')
# Make sure headless mode is OFF for debugging
# options.add_argument('--headless')  # Keep this commented out
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
# Add user-agent to mimic real browser
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.183 Safari/537.36')
service = Service('H:\\DataAnalytics_project\\real_estate_analysis\\chromedriver-win64\\chromedriver.exe')
driver = webdriver.Chrome(service=service, options=options)

# Set longer page load timeout
print('Setting page load timeout to 180 seconds...')
driver.set_page_load_timeout(180)

# Try loading the base URL first, then /#/home
try:
    print('Loading base Gujarat RERA URL...')
    driver.get('https://gujrera.gujarat.gov.in/')
    print('Base URL loaded. Now loading /#/home ...')
    driver.get('https://gujrera.gujarat.gov.in/#/home')
    print('Home URL loaded.')
    print('Current URL:', driver.current_url)
    print('First 1000 chars of page source:')
    print(driver.page_source[:1000])
except Exception as e:
    print('Error loading page:', e)

wait = WebDriverWait(driver, 20)
actions = ActionChains(driver)

import traceback

# Helper functions (top-level) for Project Profile and Partners
def get_project_profile_value(label_text):
    try:
        xpath = f"//ul[contains(@class, 'pd')]/li/p[contains(., '{label_text}')]/strong"
        el = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, xpath)))
        val_text = el.text.strip()
        nums = re.findall(r'\d+', val_text)
        if nums:
            print(f"[DEBUG] {label_text}: {nums[0]}")
            return nums[0]
    except Exception as e:
        print(f"[DEBUG] Could not extract {label_text}: {e}")
    return ""

def get_project_profile_text(label_text):
    try:
        p_xpath = (
            "//p["
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            f"'{label_text.lower()}')"
            "]"
        )
        p_elements = driver.find_elements(By.XPATH, p_xpath)
        if not p_elements:
            p_el = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, p_xpath)))
            p_elements = [p_el]
        for p_el in p_elements:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", p_el)
            except Exception:
                pass
            try:
                strong_el = p_el.find_element(By.XPATH, ".//strong")
                for _ in range(20):
                    val_text = strong_el.text.strip()
                    if val_text:
                        return val_text
                    try:
                        link = strong_el.find_element(By.XPATH, ".//a")
                        link_text = link.text.strip() or (link.get_attribute('href') or '').strip()
                        if link_text:
                            return link_text
                    except Exception:
                        pass
                    time.sleep(0.25)
            except Exception:
                pass
            try:
                following_strong = p_el.find_element(By.XPATH, "following-sibling::strong[1]")
                for _ in range(20):
                    val_text = following_strong.text.strip()
                    if val_text:
                        return val_text
                    time.sleep(0.25)
            except Exception:
                pass
            try:
                link = p_el.find_element(By.XPATH, ".//a")
                link_text = link.text.strip() or (link.get_attribute('href') or '').strip()
                if link_text:
                    return link_text
            except Exception:
                pass
            try:
                span_el = p_el.find_element(By.XPATH, ".//span")
                span_text = span_el.text.strip()
                if span_text:
                    return span_text
            except Exception:
                pass
            try:
                script = """
                    const p = arguments[0];
                    let afterBr = false;
                    for (const node of p.childNodes) {
                        if (node.nodeName === 'BR') { afterBr = true; continue; }
                        if (!afterBr) { continue; }
                        if (node.nodeType === Node.TEXT_NODE) {
                            const t = (node.textContent || '').trim();
                            if (t) { return t; }
                        }
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            const t = (node.innerText || node.textContent || '').trim();
                            if (t) { return t; }
                        }
                    }
                    return '';
                """
                js_val = driver.execute_script(script, p_el)
                if js_val:
                    return js_val.strip()
            except Exception:
                pass
            try:
                text_block = p_el.get_attribute('innerText') or p_el.text
                text_block = (text_block or '').strip()
                lowered_label = label_text.lower()
                lines = [ln.strip() for ln in re.split(r"[\r\n]+", text_block) if ln.strip()]
                if lines:
                    label_idx = None
                    for i, ln in enumerate(lines):
                        if lowered_label in ln.lower():
                            label_idx = i
                            break
                    if label_idx is not None:
                        for j in range(label_idx + 1, len(lines)):
                            candidate = lines[j].strip()
                            if candidate and candidate.lower() != lowered_label:
                                return candidate
                        same_line = lines[label_idx]
                        same_line_val = re.sub(rf"^\s*{re.escape(label_text)}\s*[:\-]*\s*", "", same_line, flags=re.IGNORECASE).strip()
                        if same_line_val and same_line_val.lower() != lowered_label:
                            return same_line_val
                    else:
                        stripped = re.sub(rf"^\s*{re.escape(label_text)}\s*[:\-]*\s*", "", text_block, flags=re.IGNORECASE).strip()
                        if stripped and stripped.lower() != lowered_label:
                            return stripped
            except Exception:
                pass
        body_txt = driver.find_element(By.TAG_NAME, 'body').text or ''
        pattern = rf"{re.escape(label_text)}\s*[\:\-]*\s*(?:\r?\n)?\s*([^\r\n]{1,100})"
        m = re.search(pattern, body_txt, flags=re.IGNORECASE)
        if m:
            candidate = (m.group(1) or '').strip()
            candidate = re.sub(r"\s{2,}.*$", "", candidate)
            return candidate
        return ""
    except Exception as e:
        print(f"[DEBUG] Could not extract text for {label_text}: {e}")
        return ""

def extract_label_from_container(container, label_text):
    try:
        p_nodes = container.find_elements(
            By.XPATH,
            (
                ".//p[contains(@class,'justify-content-between') and "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '" + label_text.lower() + "')]"
            )
        )
        if not p_nodes:
            p_nodes = container.find_elements(
                By.XPATH,
                ".//p[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '" + label_text.lower() + "')]"
            )
        for p_el in p_nodes:
            try:
                last_span = p_el.find_element(By.XPATH, ".//span[last()]")
                span_txt = last_span.text.strip()
                if span_txt and label_text.lower() not in span_txt.lower():
                    return span_txt
            except Exception:
                pass
            try:
                strong_el = p_el.find_element(By.XPATH, ".//strong")
                txt = strong_el.text.strip()
                if txt:
                    return txt
                try:
                    a_el = strong_el.find_element(By.XPATH, ".//a")
                    atxt = a_el.text.strip() or (a_el.get_attribute('href') or '').strip()
                    if atxt:
                        return atxt
                except Exception:
                    pass
            except Exception:
                pass
            try:
                last_desc_txt = p_el.find_element(By.XPATH, ".//*[last()]").text.strip()
                if last_desc_txt and label_text.lower() not in last_desc_txt.lower():
                    return last_desc_txt
            except Exception:
                pass
            try:
                a_el = p_el.find_element(By.XPATH, ".//a")
                atxt = a_el.text.strip() or (a_el.get_attribute('href') or '').strip()
                if atxt:
                    return atxt
            except Exception:
                pass
            try:
                span_el = p_el.find_element(By.XPATH, ".//span")
                stxt = span_el.text.strip()
                if stxt:
                    return stxt
            except Exception:
                pass
            try:
                js = """
                    const p = arguments[0];
                    let after = false;
                    for (const node of p.childNodes) {
                        if (node.nodeName === 'BR') { after = true; continue; }
                        if (!after) continue;
                        if (node.nodeType === Node.TEXT_NODE) {
                            const t = (node.textContent||'').trim();
                            if (t) return t;
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            const t = (node.innerText||node.textContent||'').trim();
                            if (t) return t;
                        }
                    }
                    return '';
                """
                js_val = driver.execute_script(js, p_el)
                if js_val:
                    return js_val.strip()
            except Exception:
                pass
            try:
                text_block = (p_el.get_attribute('innerText') or p_el.text or '').strip()
                m = re.search(rf"{re.escape(label_text)}\s*[:\-\uFF1A]*\s*([^\r\n]+)$", text_block, flags=re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    if val:
                        return val
                lines = [ln.strip() for ln in re.split(r"[\r\n]+", text_block) if ln.strip()]
                if lines:
                    for i, ln in enumerate(lines):
                        if label_text.lower() in ln.lower():
                            if i + 1 < len(lines):
                                val = lines[i+1].strip()
                                if val:
                                    return val
                    same = re.sub(rf"^\s*{re.escape(label_text)}\s*[:\-]*\s*", "", lines[0], flags=re.IGNORECASE).strip()
                    if same:
                        return same
            except Exception:
                pass
    except Exception:
        pass
    return ''

try:
    print('Waiting for home page to load...')
    search_bar = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@placeholder, "Project, Agent, Promoter")]')))
    print('Typing "district" in search bar and pressing Enter...')
    search_bar.clear()
    search_bar.send_keys('380006')
    search_bar.send_keys(u'\ue007')  # Press Enter key
    time.sleep(3)
    print('Waiting for filter panel link (id=clickForFilter) to appear...')
    filter_panel_link = wait.until(EC.element_to_be_clickable((By.ID, 'clickForFilter')))
    filter_panel_link.click()
    print('Clicked filter panel link. Waiting for district dropdown...')
    district_dropdown = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'select[formcontrolname="distName"]'))
    )
    print('Selecting Ahmedabad in district dropdown...')
    # Click the dropdown to expand
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", district_dropdown)
    actions.move_to_element(district_dropdown).click().perform()
    time.sleep(1)
    # Use Selenium's Select class for standard <select>
    from selenium.webdriver.support.ui import Select
    print('Selecting Ahmedabad in district dropdown using Select class...')
    select = Select(district_dropdown)
    select.select_by_visible_text('Ahmedabad')
    print('Ahmedabad selected.')
    time.sleep(1)
    print('Ahmedabad selected. Scrolling to Apply button (as <a> tag)...')
    apply_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.fBtn.applyButtonCl')))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_btn)
    time.sleep(0.5)
    print('Clicking Apply <a> button...')
    apply_btn.click()
    print('Clicked Apply. Waiting for project cards/results to load...')
    time.sleep(8)
    print('Project results should now be visible.')

    # 5. Remove all filters except PROJECT in summary bar
    try:
        # Wait for filter summary bar to appear
        summary_ul = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.search_hist_list ul')))
        li_filters = summary_ul.find_elements(By.TAG_NAME, 'li')
        for li in li_filters:
            try:
                filter_label = li.text.strip().upper()
                if filter_label != 'PROJECT' and filter_label != '':
                    x_btn = li.find_element(By.TAG_NAME, 'a')
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", x_btn)
                    x_btn.click()
                    print(f"[INFO] Removed filter: {filter_label}")
                    time.sleep(0.7)  # Wait for UI update
            except Exception as cancel_e:
                print(f"[WARNING] Could not remove filter: {cancel_e}")
                continue
        time.sleep(1)  # Wait for UI to settle after removals
    except Exception as e:
        print(f"[WARNING] Could not process filter summary bar: {e}")
        # Continue anyway

    # Clear filters (UL/LI list) except the one whose label contains 'PROJECT'
    try:
        print('[DEBUG] Attempting to clear non-Project filters (UL/LI)...')
        # Give DOM a moment to render the filter list
        time.sleep(1.5)
        removed_total = 0
        for _ in range(3):  # up to three passes in case the list re-renders
            removed_this_pass = 0
            li_nodes = driver.find_elements(By.XPATH, "//ul/li[a[contains(@href,'javascript:void')]]")
            for li in li_nodes:
                try:
                    # Extract filter label from the LI's text node (ignoring the anchor text)
                    label = driver.execute_script(
                        """
                        const li = arguments[0];
                        let name = '';
                        for (const n of li.childNodes) {
                            if (n.nodeType === Node.TEXT_NODE) {
                                const t = (n.textContent||'').trim();
                                if (t) { name = t; break; }
                            }
                        }
                        return name;
                        """,
                        li
                    ) or ''
                    label_up = str(label).strip().toUpperCase()
                    if 'PROJECT' in label_up:
                        continue
                    # Click the remove anchor inside this LI
                    try:
                        close_a = li.find_element(By.XPATH, ".//a[contains(@href,'javascript:void')][last()]")
                    except Exception:
                        close_a = None
                    if close_a is not None:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", close_a)
                        time.sleep(0.15)
                        try:
                            close_a.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", close_a)
                        removed_this_pass += 1
                        time.sleep(0.15)
                except Exception:
                    continue
            removed_total += removed_this_pass
            if removed_this_pass == 0:
                break
        print(f"[DEBUG] Removed {removed_total} non-Project filter(s).")
    except Exception as e:
        print(f"[DEBUG] Could not clear filters via UL/LI: {e}")

    # Scroll down slightly to bring cards into view
    driver.execute_script('window.scrollBy(0, 250);')
    time.sleep(1)
    
    # Implement lazy loading to get all projects
    print("Loading all projects by scrolling to trigger lazy loading...")
    previous_count = 0
    scroll_attempts = 0
    max_scroll_attempts = 50  # Prevent infinite scrolling
    
    while scroll_attempts < max_scroll_attempts:
        # Get current count of project cards
        view_more_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.vmore.mb-2')
        current_count = len(view_more_buttons)
        
        print(f"Currently found {current_count} project cards...")
        
        # Check if new projects were loaded
        if current_count == previous_count:
            # Try scrolling to bottom to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for new content to load
            
            # Check again after scrolling
            view_more_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.vmore.mb-2')
            new_count = len(view_more_buttons)
            
            if new_count == current_count:
                # No new projects loaded after scrolling, we've reached the end
                print(f"No more projects loading. Total found: {current_count}")
                break
            else:
                current_count = new_count
        
        previous_count = current_count
        scroll_attempts += 1
        
        # Scroll to bottom to load more
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Wait for lazy loading
    
    # Final count of all projects
    view_more_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.vmore.mb-2')
    total_projects = len(view_more_buttons)
    print(f"Found total of {total_projects} project cards to process after lazy loading.")
    
    # Scroll back to top before processing
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)
    
    for project_index in range(total_projects):
        try:
            print(f"\n=== Processing Project {project_index + 1} of {total_projects} ===")
            # Re-find buttons each loop to avoid stale references
            view_more_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.vmore.mb-2')
            if project_index >= len(view_more_buttons):
                print(f"Project {project_index + 1} not found. Stopping.")
                break
            view_more_btn = view_more_buttons[project_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", view_more_btn)
            print('Clicking View More...')
            view_more_btn.click()
            print('Clicked View More. Waiting for project details page to load...')
            time.sleep(3)
            # Wait for a known details field to appear
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Project Name') or contains(text(), 'Registration') or contains(text(), 'Promoter') or contains(text(), 'Builder') or contains(text(), 'Address') or contains(text(), 'Locality') or contains(text(), 'Unit') or contains(text(), 'Price') or contains(text(), 'Completion') or contains(text(), 'Status') or contains(text(), 'Start Date') or contains(text(), 'End Date') or contains(text(), 'Available') or contains(text(), 'Sold') or contains(text(), 'Type') or contains(text(), 'RERA') or contains(text(), 'Reg No') or contains(text(), 'Date') or contains(text(), 'Status') or contains(text(), 'Type') or contains(text(), 'Unit') or contains(text(), 'Price')]") ))
            print('Details page should now be visible.')

            # Scroll down the details page in increments to load all sections
            print('Scrolling through the details page to load all sections...')
            last_height = driver.execute_script('return document.body.scrollHeight')
            for y in range(0, last_height, 400):
                driver.execute_script(f'window.scrollTo(0, {y});')
                time.sleep(0.5)
            time.sleep(1)
            
            # Specifically scroll to About Property section
            try:
                print('Scrolling to About Property section...')
                about_property_selectors = [
                    "//td[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'about property')]",
                    "//strong[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'about property')]",
                    "//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'about property')]",
                    "//div[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'about property')]"
                ]
                
                about_property_found = False
                for selector in about_property_selectors:
                    try:
                        elements = driver.find_elements(By.XPATH, selector)
                        for element in elements:
                            if element.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(2)
                                print('Scrolled to About Property section')
                                about_property_found = True
                                break
                        if about_property_found:
                            break
                    except Exception:
                        continue
                
                if not about_property_found:
                    print('About Property section not found, continuing with extraction...')
                    
            except Exception as e:
                print(f'Error scrolling to About Property section: {e}')

            print('Extracting Project Name and RERA Registration Number...')
            project_data = {
                'Pincode': '380006',  # Add pincode column
                'Project Name': '',
                'RERA Reg. No.': '',
                'Project Address': '',
                'Project Type': '',
                'About Property': '',
                'Project Start Date': '',
                'Project End Date': '',
                'Project Land Area': '',
                'Total Open Area': '',
                'Total Covered Area': '',
                'Carpet Area of Units (Range)': '',
                'Plan Passing Authority': '',
                'Amenities': '',
                'Total Units': '',
                'Available Units': '',
                'Total No. of Towers/Blocks': '',
                'Promoter Name': '',
                'Promoter Type': '',
                'Office Address': ''
                # Partner columns will be added dynamically below
            }
            type_details_rows = []

            # Extract Project Name (do not overwrite if already found)
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'project name')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Project Name:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Project Name'] = value
                        break
                except Exception:
                    continue
            # Extract RERA Reg. No. (do not overwrite if already found)
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'gujrera reg. no.')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'GUJRERA Reg. No.:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['RERA Reg. No.'] = value
                        break
                except Exception:
                    continue
            # Extract Project Address (do not overwrite if already found)
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'project address')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Project Address:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Project Address'] = value
                        break
                except Exception:
                    continue
            # Extract Taluka, District, State (from a single td containing labels)
            try:
                td = driver.find_element(
                    By.XPATH,
                    "//td[contains(@class,'no-print') and contains(., 'Taluka:-') and contains(., 'District:-') and contains(., 'State:-')]"
                )
                text = td.text.strip()
                # Example text: "Taluka:- Ahmedabad City, District:- Ahmedabad, State:- GUJARAT"
                taluka = ''
                district = ''
                state = ''
                m = re.search(r"Taluka:-\s*([^,\n]+)", text, flags=re.IGNORECASE)
                if m:
                    taluka = m.group(1).strip()
                m = re.search(r"District:-\s*([^,\n]+)", text, flags=re.IGNORECASE)
                if m:
                    district = m.group(1).strip()
                m = re.search(r"State:-\s*([^,\n]+)", text, flags=re.IGNORECASE)
                if m:
                    state = m.group(1).strip()
                # Save right after Project Address to preserve column order
                if taluka:
                    project_data['Taluka'] = taluka
                if district:
                    project_data['District'] = district
                if state:
                    project_data['State'] = state
            except Exception:
                pass
            # Extract Project Type
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'project type')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Project Type:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Project Type'] = value
                        break
                except Exception:
                    continue
            # Extract About Property
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'about property')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'About Property:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['About Property'] = value
                        break
                except Exception:
                    continue
            # Extract Project Start Date
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'project start date')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Project Start Date:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Project Start Date'] = value
                        break
                except Exception:
                    continue
            # Extract Project End Date
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'project end date')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Project End Date:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Project End Date'] = value
                        break
                except Exception:
                    continue
            # Extract Project Land Area
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'project land area')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Project Land Area:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Project Land Area'] = value
                        break
                except Exception:
                    continue
            # Extract Total Open Area
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'total open area')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Total Open Area:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Total Open Area'] = value
                        break
                except Exception:
                    continue
            # Extract Total Covered Area
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'total covered area')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Total Covered Area:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Total Covered Area'] = value
                        break
                except Exception:
                    continue
            # Extract Carpet Area of Units (Range)
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'carpet area of units (range)')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Carpet Area of Units (Range)[:-]'
                    idx = full_text.find('Carpet Area of Units (Range):-')
                    if idx != -1:
                        value = full_text[idx+len('Carpet Area of Units (Range):-'):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if 'Carpet Area of Units (Range):-' in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Carpet Area of Units (Range)'] = value
                        break
                except Exception:
                    continue
            # Extract Plan Passing Authority
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'plan passing authority')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Plan Passing Authority:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Plan Passing Authority'] = value
                        break
                except Exception:
                    continue
            # Extract Redevelopment Project and Affordable Housing flags from the same summary row
            try:
                # Prefer the <tr> that also includes Plan Passing Authority (same row in provided HTML)
                tr = driver.find_element(
                    By.XPATH,
                    "//tr[.//strong[contains(., 'Plan Passing')]]"
                )
                txt = tr.text.strip()
                # Examples in combined row:
                # "Plan Passing Authority:- XYZ  Redevelopment Project:- NO  Affordable Housing :- YES"
                m = re.search(r"Redevelopment\s*Project:-\s*([^\n\r]+?)(?:\s{2,}|\s+$|$)", txt, flags=re.IGNORECASE)
                if m:
                    redevelopment_val = m.group(1).strip().strip(',')
                    if redevelopment_val.upper() == 'NIL':
                        redevelopment_val = 'NO'
                    project_data['Redevelopment Project'] = redevelopment_val
                m = re.search(r"Affordable\s*Housing\s*:-\s*([^\n\r]+?)(?:\s{2,}|\s+$|$)", txt, flags=re.IGNORECASE)
                if m:
                    affordable_val = m.group(1).strip().strip(',')
                    project_data['Affordable Housing'] = affordable_val
            except Exception:
                # Fallback: search anywhere in the page
                try:
                    body_txt = driver.find_element(By.TAG_NAME, 'body').text
                    m = re.search(r"Redevelopment\s*Project:-\s*([^\n\r]+)", body_txt, flags=re.IGNORECASE)
                    if m:
                        redevelopment_val = m.group(1).strip().strip(',')
                        if redevelopment_val.upper() == 'NIL':
                            redevelopment_val = 'NO'
                        project_data['Redevelopment Project'] = redevelopment_val
                    m = re.search(r"Affordable\s*Housing\s*:-\s*([^\n\r]+)", body_txt, flags=re.IGNORECASE)
                    if m:
                        affordable_val = m.group(1).strip().strip(',')
                        project_data['Affordable Housing'] = affordable_val
                except Exception:
                    pass
            # Extract Amenities (all <p> tags inside the table after 'Common Amenities' <strong>)
            amenities = []
            try:
                # Find the 'Common Amenities' <strong>
                amenity_labels = driver.find_elements(By.XPATH, "//strong[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'common amenities')]")
                for label in amenity_labels:
                    # Find the closest following table (regardless of nesting)
                    table = None
                    try:
                        table = label.find_element(By.XPATH, "ancestor::td/following::table[1]")
                    except Exception:
                        try:
                            table = label.find_element(By.XPATH, "ancestor::tr/following::tr//table[1]")
                        except Exception:
                            continue
                    if table:
                        ps = table.find_elements(By.XPATH, ".//p")
                        for p in ps:
                            amenity = p.text.strip()
                            if amenity and amenity.lower() not in [a.lower() for a in amenities]:
                                amenities.append(amenity)
                        break  # Only take the first matching amenities table
            except Exception:
                pass
            if amenities:
                project_data['Amenities'] = ', '.join(amenities)

            # Removed: Do not store 'Booked Units as on' / 'Un-booked Units as on'

            # Extract 'Type Details' table: Unit Type, Block, Booked/Un-booked Units
            try:
                # Locate the table that has a header cell with 'Type Details'
                type_label = driver.find_element(By.XPATH, "//strong[contains(normalize-space(.), 'Type Details')]")
                type_table = type_label.find_element(By.XPATH, "ancestor::table[1]")

                # Read headers
                headers = [th.text.strip() for th in type_table.find_elements(By.XPATH, ".//thead//th")]
                if not headers:
                    # Fallback: sometimes headers are in the second row of thead
                    headers = [th.text.strip() for th in type_table.find_elements(By.XPATH, ".//thead//tr[last()]//th")]

                # Helper to find column index by fuzzy header match
                def find_col_idx(target):
                    t = target.lower()
                    for i, h in enumerate(headers):
                        low = h.lower()
                        if 'unit type' in t and ('unit' in low and 'type' in low):
                            return i
                        if t == 'block' and 'block' in low:
                            return i
                        if 'booked units as on' in t and 'booked' in low:
                            return i
                        if 'un-booked units as on' in t and ('un-booked' in low or 'unbooked' in low):
                            return i
                    return None

                idx_unit = find_col_idx('Unit Type')
                idx_block = find_col_idx('Block')
                idx_booked = None
                idx_unbooked = None

                vals_unit, vals_block = [], []
                rows = type_table.find_elements(By.XPATH, ".//tbody//tr")
                for r in rows:
                    cells = r.find_elements(By.XPATH, ".//td")
                    def safe_get(idx):
                        try:
                            return cells[idx].text.strip()
                        except Exception:
                            return ''
                    if idx_unit is not None:
                        v = safe_get(idx_unit)
                        if v:
                            vals_unit.append(v)
                    if idx_block is not None:
                        v = safe_get(idx_block)
                        if v:
                            vals_block.append(v)
                    # Booked/Un-booked columns intentionally ignored

                if vals_unit:
                    project_data['Unit Type'] = '; '.join(vals_unit)
                if vals_block:
                    project_data['Block'] = '; '.join(vals_block)
                # Only set from Type Details if summary page didn't already populate
                # Do not set Booked/Un-booked fields
            except Exception:
                pass

            # Extract financial summary: Project Estimated Cost and Percentage Loan Against Project Estimated Cost
            try:
                # Target the row that contains the labels in strong tags
                fin_row = driver.find_element(
                    By.XPATH,
                    "//tr[.//strong[contains(normalize-space(.), 'Project Estimated Cost')]]"
                )

                def extract_from_row(label_xpath, label_regex):
                    try:
                        strong = fin_row.find_element(By.XPATH, label_xpath)
                        td = strong.find_element(By.XPATH, "ancestor::td[1]")
                        text = td.text.strip()
                        m = re.search(label_regex, text, flags=re.IGNORECASE)
                        if m:
                            val = m.group(1).strip()
                            # Normalize placeholders (preserve 'NIL' as-is)
                            if val.upper() in {'NA', 'N/A', 'NONE', 'NULL'} or val.upper().startswith('NAN'):
                                return ''
                            return val
                    except Exception:
                        return ''
                    return ''

                cost_val = extract_from_row(
                    ".//strong[contains(normalize-space(.), 'Project Estimated Cost')]",
                    r"Project\s*Estimated\s*Cost\s*\(Rs\.\)\s*:-\s*(.*)$"
                )
                if cost_val:
                    project_data['Project Estimated Cost (Rs.)'] = cost_val

                pct_val = extract_from_row(
                    ".//strong[contains(normalize-space(.), 'Percentage Loan Against Project Estimated Cost')]",
                    r"Percentage\s*Loan\s*Against\s*Project\s*Estimated\s*Cost\s*:-\s*(.*)$"
                )
                if pct_val:
                    project_data['Percentage Loan Against Project Estimated Cost'] = pct_val
            except Exception:
                pass

            # Extract Compliance metrics from summary page
            try:
                def extract_label_value_exact(label_text_base):
                    """Find a <strong> containing label_text_base (no punctuation required); return trailing text in the same <td>."""
                    try:
                        strong = driver.find_element(By.XPATH, f"//strong[contains(normalize-space(.), '{label_text_base}')]")
                        td = strong.find_element(By.XPATH, "ancestor::td[1]")
                        text = td.text.strip()
                        # Build regex that tolerates optional spaces/colon/hyphen sequences
                        pattern = rf"{re.escape(label_text_base)}\s*:?\s*-?\s*(.*)$"
                        m = re.search(pattern, text, flags=re.IGNORECASE)
                        if m:
                            val = m.group(1).strip()
                            # Preserve 'NIL' for compliance fields; treat other placeholders as empty
                            if val.upper() in {'NA', 'N/A', 'NONE', 'NULL'} or val.upper().startswith('NAN'):
                                return ''
                            return val
                    except Exception:
                        return ''
                    return ''

                q_required = extract_label_value_exact('Total Quarterly Compliance Required')
                if q_required:
                    project_data['Total Quarterly Compliance Required'] = q_required

                q_complied = extract_label_value_exact('Total Complied Quarters')
                if q_complied:
                    project_data['Total Complied Quarters'] = q_complied

                q_defaulted = extract_label_value_exact('Total Quarterly Compliance Defaulted')
                if q_defaulted:
                    project_data['Total Quarterly Compliance Defaulted'] = q_defaulted

                a_required = extract_label_value_exact('Total Annual Compliance Required')
                if a_required:
                    project_data['Total Annual Compliance Required'] = a_required

                a_complied = extract_label_value_exact('Total Complied Annual Compliance')
                if a_complied:
                    project_data['Total Complied Annual Compliance'] = a_complied

                a_defaulted = extract_label_value_exact('Total Annual Compliance Defaulted')
                if a_defaulted:
                    project_data['Total Annual Compliance Defaulted'] = a_defaulted
            except Exception:
                pass

            # Ensure financial and compliance keys exist so CSV gains headers even if values missing
            for _k in [
        'Project Estimated Cost (Rs.)',
        'Percentage Loan Against Project Estimated Cost',
        'Total Quarterly Compliance Required',
        'Total Complied Quarters',
        'Total Quarterly Compliance Defaulted',
        'Total Annual Compliance Required',
        'Total Complied Annual Compliance',
        'Total Annual Compliance Defaulted',
            ]:
                if _k not in project_data:
                    project_data[_k] = ''

            import re
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            # removed stray placeholder
            def get_li_value(label, timeout_seconds: float = 12.0, stable_reads_required: int = 2):
                """Read a numeric summary value under ul.pd for the given label, waiting for dynamic updates to settle.

                Strategy per attempt:
                - strong inside the label <p>
                - following sibling element
                - next line after label within the same <p>
                - inline "Label: 12" within the same <p>
                We poll until we observe a stable value (same read repeated) and, preferably, non-zero.
                """
                start_ts = time.time()
                last_val = None
                stable_reads = 0

                def read_once() -> str:
                    # Case-insensitive locator for the <p> with the label
                    p_xpath = (
                        "//ul[contains(@class, 'pd')]/li/p["
                        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
                        f"'{label.lower()}')"
                        "]"
                    )
                try:
                    # Try direct strong under the <p>
                    strong_xpath = p_xpath + "/strong"
                    element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, strong_xpath)))
                    txt = (element.text or '').strip()
                    nums = re.findall(r"\d+", txt)
                    if nums:
                        return nums[0]
                except Exception:
                    pass
                try:
                    p_el = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, p_xpath)))
                    # Following sibling element
                    try:
                        sib = p_el.find_element(By.XPATH, "following-sibling::*[1]")
                        txt = (sib.text or '').strip()
                        nums = re.findall(r"\d+", txt)
                        if nums:
                            return nums[0]
                    except Exception:
                        pass
                    # Next line after label in the same <p>
                    text_block = (p_el.get_attribute('innerText') or p_el.text or '').strip()
                    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text_block) if ln.strip()]
                    if len(lines) >= 2:
                        for i, ln in enumerate(lines):
                            if label.lower() in ln.lower() and i + 1 < len(lines):
                                nxt = lines[i + 1]
                                nums = re.findall(r"\d+", nxt)
                                if nums:
                                    return nums[0]
                    # Inline label: value
                    m = re.search(rf"{re.escape(label)}\s*[:\-]*\s*(\d+)", text_block, flags=re.IGNORECASE)
                    if m:
                        return m.group(1)
                except Exception:
                    pass
                return ""

                while time.time() - start_ts < timeout_seconds:
                    val = read_once()
                    if val:
                        if val == last_val:
                            stable_reads += 1
                        else:
                            last_val = val
                            stable_reads = 1
                        # Prefer a non-zero stable value; otherwise accept any value that stabilizes
                        if (val != '0' and stable_reads >= stable_reads_required) or stable_reads >= (stable_reads_required + 1):
                            print(f"[DEBUG] {label} (stable): {val}")
                            return val
                    time.sleep(0.3)
                # Timeout: return last seen value (may be '0' if truly zero or page failed to load fully)
                print(f"[DEBUG] {label} (timeout, last='{last_val}')")
                return last_val or ""

            print("[DEBUG] Starting extraction...")

            project_data['Total Units'] = get_li_value("Total Units")
            project_data['Available Units'] = get_li_value("Available Units")
            # Try multiple label variants for towers/blocks
            def get_towers_blocks():
                labels = [
                    "Total No. of Towers/Blocks",
                    "Total No. of Towers",
                    "Total Towers",
                    "Total Blocks",
                    "Towers/Blocks",
                    "Towers",
                    "Blocks",
                ]
                for lbl in labels:
                    v = get_li_value(lbl)
                    if v:
                        return v
                return ""
            project_data['Total No. of Towers/Blocks'] = get_towers_blocks()

            print("[DEBUG] Extraction complete:", project_data)

            # Extract Promoter Name
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'promoter name')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Promoter Name:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Promoter Name'] = value
                        break
                except Exception:
                    continue
            # Extract Promoter Type
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'promoter type')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Promoter Type:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Promoter Type'] = value
                        break
                except Exception:
                    continue
            # Extract Office Address
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'office address')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Office Address:-'
                    idx = full_text.find(marker)
                    if idx != -1:
                        value = full_text[idx+len(marker):].strip()
                        if not value and '\n' in full_text:
                            lines = full_text.split('\n')
                            for i, line in enumerate(lines):
                                if marker in line:
                                    if i+1 < len(lines):
                                        value = lines[i+1].strip()
                                    break
                        if value:
                            project_data['Office Address'] = value
                        break
                except Exception:
                    continue
            # Extract Partners (all numbered items after 'Partners:-'), each as its own column
            td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'partners')]")
            for td in td_elems:
                try:
                    full_text = td.text.strip()
                    marker = 'Partners:-'
                    idx = full_text.find(marker)
                    partners = []
                    if idx != -1:
                        # Get everything after 'Partners:-', split by lines
                        after = full_text[idx+len(marker):].strip()
                        lines = after.split('\n')
                        for line in lines:
                            # Match lines like '1. NAME ...' or '2. NAME ...'
                            if line.strip() and (line.strip()[0].isdigit() and '.' in line):
                                # Remove number and dot
                                partner = line.split('.', 1)[1].strip()
                                if partner:
                                    partners.append(partner)
                        # Add each partner to its own column
                        for i, partner in enumerate(partners):
                            project_data[f'Partner {i+1}'] = partner
                        break
                except Exception:
                    continue
    # Extract Type Details table rows (Unit Type, Block, Total Units)
    # # Robustly extract the Type Details table by header content, not by label proximity
    # try:
    #     type_details_found = False
    #     tables = driver.find_elements(By.XPATH, "//table")
    #     for table in tables:
    #         headers = table.find_elements(By.XPATH, ".//th")
    #         header_texts = [th.text.strip().lower() for th in headers]
    #         # Look for all required headers
    #         if ('unit type' in header_texts and 'block' in header_texts and 'total units' in header_texts):
    #             print(f"[DEBUG] Type Details table found with headers: {header_texts}")
    #             rows = table.find_elements(By.XPATH, ".//tr")
    #             if not rows or len(rows) < 2:
    #                 print("[DEBUG] Type Details table is empty or has only header.")
    #                 continue
    #             headers = [th.text.strip() for th in rows[0].find_elements(By.XPATH, ".//th")]
    #             print(f"[DEBUG] Headers found: {headers}")
    #             for row in rows[1:]:
    #                 cells = row.find_elements(By.XPATH, ".//td")
    #                 if len(cells) == len(headers):
    #                     row_dict = {headers[i]: cells[i].text.strip() for i in range(len(headers))}
    #                     print(f"[DEBUG] Extracted row: {row_dict}")
    #                     if any(row_dict.values()):
    #                         type_details_rows.append(row_dict)
    #             type_details_found = True
    #             break
    #     if not type_details_found:
    #         print("[DEBUG] No Type Details table found with required headers.")
    # except Exception as e:
    #     print('Type Details extraction error:', e)
    #     pass
    
            # ✅ Click on "Project Profile" tab
            try:
                project_profile_tab = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(), 'Project Profile')]")
                ))
                project_profile_tab.click()
                print("[DEBUG] Clicked 'Project Profile' tab.")
            except Exception as e:
                print(f"[DEBUG] Could not click Project Profile tab: {e}")

            # ✅ Function to extract values from Project Profile
            def get_project_profile_value(label_text):
                """
                Find a <li> in the <ul class='pd'> where the <p> contains the label_text,
                then extract the number from its <strong> tag.
                """
                try:
                    xpath = f"//ul[contains(@class, 'pd')]/li/p[contains(., '{label_text}')]/strong"
                    el = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                    val_text = el.text.strip()
                    nums = re.findall(r'\d+', val_text)
                    if nums:
                        print(f"[DEBUG] {label_text}: {nums[0]}")
                        return nums[0]
                except Exception as e:
                    print(f"[DEBUG] Could not extract {label_text}: {e}")
                return ""

            # ✅ Robust text extractor from Project Profile (handles value in <strong>, link, or next line)
            def get_project_profile_text(label_text):
                try:
                    # 1) Locate all <p> that contain the label (case-insensitive) anywhere on the page
                    p_xpath = (
                        "//p["
                        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
                        f"'{label_text.lower()}')"
                        "]"
                    )
                    p_elements = driver.find_elements(By.XPATH, p_xpath)
                    if not p_elements:
                        p_el = wait.until(EC.presence_of_element_located((By.XPATH, p_xpath)))
                        p_elements = [p_el]

                    for p_el in p_elements:
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", p_el)
                        except Exception:
                            pass

                        # 2) Try value inside a descendant <strong>
                        try:
                            strong_el = p_el.find_element(By.XPATH, ".//strong")
                            # Wait briefly for dynamic text to populate
                            for _ in range(20):
                                val_text = strong_el.text.strip()
                                if val_text:
                                    print(f"[DEBUG] {label_text} (strong): {val_text}")
                                    return val_text
                                try:
                                    link = strong_el.find_element(By.XPATH, ".//a")
                                    link_text = link.text.strip() or (link.get_attribute('href') or '').strip()
                                    if link_text:
                                        print(f"[DEBUG] {label_text} (strong->a): {link_text}")
                                        return link_text
                                except Exception:
                                    pass
                                time.sleep(0.25)
                        except Exception:
                            pass

                        # 3) Try a following-sibling <strong>
                        try:
                            following_strong = p_el.find_element(By.XPATH, "following-sibling::strong[1]")
                            for _ in range(20):
                                val_text = following_strong.text.strip()
                                if val_text:
                                    print(f"[DEBUG] {label_text} (following-strong): {val_text}")
                                    return val_text
                                time.sleep(0.25)
                        except Exception:
                            pass

                        # 3b) Try any <a> within the <p>
                        try:
                            link = p_el.find_element(By.XPATH, ".//a")
                            link_text = link.text.strip() or (link.get_attribute('href') or '').strip()
                            if link_text:
                                print(f"[DEBUG] {label_text} (p->a): {link_text}")
                                return link_text
                        except Exception:
                            pass

                        # 3c) Try any <span> within the <p>
                        try:
                            span_el = p_el.find_element(By.XPATH, ".//span")
                            span_text = span_el.text.strip()
                            if span_text:
                                print(f"[DEBUG] {label_text} (p->span): {span_text}")
                                return span_text
                        except Exception:
                            pass

                        # 3d) Try reading text node after <br> within the same <p> using JS (handles values not wrapped in tags)
                        try:
                            script = """
                                const p = arguments[0];
                                let afterBr = false;
                                for (const node of p.childNodes) {
                                    if (node.nodeName === 'BR') { afterBr = true; continue; }
                                    if (!afterBr) { continue; }
                                    if (node.nodeType === Node.TEXT_NODE) {
                                        const t = (node.textContent || '').trim();
                                        if (t) { return t; }
                                    }
                                    if (node.nodeType === Node.ELEMENT_NODE) {
                                        const t = (node.innerText || node.textContent || '').trim();
                                        if (t) { return t; }
                                    }
                                }
                                return '';
                            """
                            js_val = driver.execute_script(script, p_el)
                            if js_val:
                                print(f"[DEBUG] {label_text} (p->after<br> text): {js_val}")
                                return js_val.strip()
                        except Exception:
                            pass

                        # 4) Parse the text content of the <p> to extract anything after the label
                        try:
                            text_block = p_el.get_attribute('innerText') or p_el.text
                            text_block = (text_block or '').strip()
                            # Remove label prefix on the first line if present
                            # Example: "Project Status\nNew" or "Project Status New"
                            lowered_label = label_text.lower()
                            # Prefer next non-empty line after a line containing the label
                            lines = [ln.strip() for ln in re.split(r"[\r\n]+", text_block)]
                            lines = [ln for ln in lines if ln]
                            if lines:
                                label_idx = None
                                for i, ln in enumerate(lines):
                                    if lowered_label in ln.lower():
                                        label_idx = i
                                        break
                                if label_idx is not None:
                                    # Return first non-empty line after label line
                                    for j in range(label_idx + 1, len(lines)):
                                        candidate = lines[j].strip()
                                        if candidate and candidate.lower() != lowered_label:
                                            print(f"[DEBUG] {label_text} (p-lines next): {candidate}")
                                            return candidate
                                    # If same line also contains value (e.g., "Label : Value")
                                    same_line = lines[label_idx]
                                    same_line_val = re.sub(rf"^\s*{re.escape(label_text)}\s*[:\-]*\s*", "", same_line, flags=re.IGNORECASE).strip()
                                    if same_line_val and same_line_val.lower() != lowered_label:
                                        print(f"[DEBUG] {label_text} (p-same-line): {same_line_val}")
                                        return same_line_val
                                else:
                                    # Label not found in split lines; try removing label prefix globally
                                    stripped = re.sub(rf"^\s*{re.escape(label_text)}\s*[:\-]*\s*", "", text_block, flags=re.IGNORECASE).strip()
                                    if stripped and stripped.lower() != lowered_label:
                                        print(f"[DEBUG] {label_text} (p-strip-prefix): {stripped}")
                                        return stripped
                        except Exception:
                            pass

                        # 5) Read the parent <li> text and try to split
                        try:
                            li_el = p_el.find_element(By.XPATH, "ancestor::li[1]")
                            li_text = (li_el.get_attribute('innerText') or li_el.text or '').strip()
                            lines = [ln.strip() for ln in re.split(r"[\r\n]+", li_text) if ln.strip()]
                            for i, ln in enumerate(lines):
                                if label_text.lower() in ln.lower() and i + 1 < len(lines):
                                    candidate = lines[i + 1]
                                    if candidate and candidate.lower() != label_text.lower():
                                        print(f"[DEBUG] {label_text} (li-lines): {candidate}")
                                        return candidate
                            # 5b) Try the first strong under this li after the label
                            try:
                                strongs = li_el.find_elements(By.XPATH, ".//strong")
                                for st in strongs:
                                    txt = st.text.strip()
                                    if txt:
                                        print(f"[DEBUG] {label_text} (li->strong): {txt}")
                                        return txt
                            except Exception:
                                pass
                        except Exception:
                            pass

                    print(f"[DEBUG] {label_text}: value not found or empty.")
                    # 6) Global page-text fallback using regex: capture text after label up to newline (or on next line)
                    try:
                        body_txt = driver.find_element(By.TAG_NAME, 'body').text or ''
                        pattern = rf"{re.escape(label_text)}\s*[\:\-]*\s*(?:\r?\n)?\s*([^\r\n]{1,100})"
                        m = re.search(pattern, body_txt, flags=re.IGNORECASE)
                        if m:
                            candidate = (m.group(1) or '').strip()
                            candidate = re.sub(r"\s{2,}.*$", "", candidate)
                            print(f"[DEBUG] {label_text} (body-regex): {candidate}")
                            return candidate
                    except Exception:
                        pass
                    return ""
                except Exception as e:
                    print(f"[DEBUG] Could not extract text for {label_text}: {e}")
                    return ""

            # ✅ Wait for <ul class="pd"> list to load
            try:
                wait.until(EC.presence_of_all_elements_located((By.XPATH, "//ul[contains(@class, 'pd')]/li")))
                print("[DEBUG] Project Profile list loaded for extraction.")
            except:
                print("[DEBUG] Could not find Project Profile list. Values may be empty.")

            # ✅ Store results
            # project_data = {}
            project_data['Total Units'] = get_project_profile_value("Total Units")
            project_data['Available Units'] = get_project_profile_value("Available Units")
            project_data['Total No. of Towers/Blocks'] = get_project_profile_value("Total No. of Towers/Blocks")
            # New profile fields
            project_data['Project Status'] = get_project_profile_text("Project Status")
            project_data['Website'] = get_project_profile_text("Website")
            project_data['Approved Date'] = get_project_profile_text("Approved Date")
    
    
            # ✅ Click on "Promoters" tab
            try:
                promoters_tab = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(), 'Promoters')]")
                ))
                promoters_tab.click()
                print("[DEBUG] Clicked 'Promoters' tab.")
            except Exception as e:
                print(f"[DEBUG] Could not click Promoters tab: {e}")

            # ✅ Wait for promoter details section to load
            try:
                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//h2[contains(text(), 'Promoter Details')]")
                ))
                print("[DEBUG] Promoter Details section loaded.")
            except:
                print("[DEBUG] Promoter Details section not detected — may be empty.")

            # ✅ Extract promoter details
            promoter_fields = {
                'Promoter Name': "//p[strong[contains(text(), 'Promoter Name')]]/span",
                'Promoter Type': "//p[strong[contains(text(), 'Promoter Type')]]/span",
                'Contact': "//p[strong[contains(text(), 'Contact')]]/span",
                'Email Id': "//p[strong[contains(text(), 'Email Id')]]/span",
                'Address': "//p[strong[contains(text(), 'Address')]]/span"
            }

            for key, xpath in promoter_fields.items():
                try:
                    elem = driver.find_element(By.XPATH, xpath)
                    value = elem.text.strip()
                    if value:
                        project_data[key] = value
                        print(f"[DEBUG] {key}: {value}")
                except Exception as e:
                    print(f"[DEBUG] Could not extract {key}: {e}")

            # ✅ Extract Partners list (Name, Email Id, Mobile) from Promoters page
            try:
                # Find all containers that look like a person card (by presence of a Name label text)
                person_containers = driver.find_elements(
                    By.XPATH,
                    (
                        "//p[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name')]/"
                        "ancestor::div[contains(@class,'avCol') or contains(@class,'col-sm-12') or contains(@class,'col-md-') or contains(@class,'col-lg-')][1]"
                    )
                )
                # Deduplicate by element id
                seen_ids = set()
                unique_containers = []
                for c in person_containers:
                    _id = c.id
                    if _id not in seen_ids:
                        unique_containers.append(c)
                        seen_ids.add(_id)

                # Identify signatory column to exclude from partners
                signatory_col = None
                try:
                    signatory_heading = driver.find_element(By.XPATH, "//h2[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'signatory details')]")
                    signatory_col = signatory_heading.find_element(By.XPATH, "ancestor::div[contains(@class,'col-') or contains(@class,'col-lg') or contains(@class,'col-sm')][1]")
                except Exception:
                    pass

                partners = []
                for container in unique_containers:
                    # Skip if belongs to signatory column
                    if signatory_col is not None:
                        try:
                            in_signatory = len(container.find_elements(By.XPATH, ".//ancestor::div[.//h2[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'signatory details')]]")) > 0
                        except Exception:
                            in_signatory = False
                        if in_signatory:
                            continue

                    name = extract_label_from_container(container, 'Name')
                    email = extract_label_from_container(container, 'Email') or extract_label_from_container(container, 'Email Id')
                    mobile = extract_label_from_container(container, 'Mobile')
                    if name or email or mobile:
                        partners.append({'name': name, 'email': email, 'mobile': mobile})

                # Write into project_data as Partner 1/2/.. with Name, Mobile, Email Id columns
                for i, p in enumerate(partners, start=1):
                    name = p.get('name', '').strip()
                    mobile = p.get('mobile', '').strip()
                    email = p.get('email', '').strip()
                    if mobile:
                        mobile = re.sub(r"\D+", "", mobile) or mobile
                    # Compose single cell value: "Name, Mobile, Email"
                    parts = [v for v in [name, mobile, email] if v]
                    if parts:
                        project_data[f'Partner {i}'] = ", ".join(parts)
                if partners:
                    print(f"[DEBUG] Extracted {len(partners)} partner entries")
                else:
                    print("[DEBUG] No partner entries found on Promoters page")
            except Exception as e:
                print(f"[DEBUG] Partners extraction error: {e}")


            # ✅ Debug output
            print("[DEBUG] Final Extracted Data:", project_data)

            # Combine all Type Details into a single row for the project
            import pandas as pd
            combined_row = project_data.copy()
            if type_details_rows:
                # Find all unique type detail columns
                type_keys = set()
                for row in type_details_rows:
                    type_keys.update(row.keys())
                # For each column, join all values with '; '
                for k in type_keys:
                    values = [row.get(k, '') for row in type_details_rows if row.get(k, '')]
                    if values:
                        combined_row[k] = '; '.join(values)
            print(f"Extracted fields: {combined_row}")
            df = pd.DataFrame([combined_row])
            append_unique_by_regno(df, 'ahmedabad_projects.csv')
            print('Saved/updated ahmedabad_projects.csv')

            # Go back to project listing for next card
            try:
                print('Returning to project listing...')
                driver.execute_script('window.scrollTo(0, 0);')
                time.sleep(1)
                driver.back()
                # Wait for any View More button to reappear
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a.vmore.mb-2')))
                time.sleep(2)
            except Exception as nav_e:
                print(f"[WARN] Could not navigate back cleanly: {nav_e}")
                # Attempt recovery by going back again
                try:
                    driver.back()
                    time.sleep(2)
                except Exception:
                    pass
        except Exception as loop_e:
            print(f"[ERROR] Failed processing project {project_index + 1}: {loop_e}")
            traceback.print_exc()
            # Try to recover to listing and continue
            try:
                driver.back()
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a.vmore.mb-2')))
                time.sleep(2)
            except Exception:
                pass

    # All projects processed
    print('All project cards processed. Exiting...')
    driver.quit()
    exit(0)

except Exception as e:
    print('Navigation or filter selection failed:', e)
    traceback.print_exc()
    driver.save_screenshot('navigation_or_filter_error.png')
    print('Screenshot saved as navigation_or_filter_error.png')
    driver.quit()
    exit(1)

except Exception as e:
    print('\nERROR during Selenium automation:')
    print(str(e))
    print('Full traceback:')
    traceback.print_exc()
    print('Taking screenshot for debugging...')
    driver.save_screenshot('selenium_error_screenshot.png')
    print('Screenshot saved as selenium_error_screenshot.png')
    print('Browser will remain open for manual inspection. Press Enter to close...')
    input()
    driver.quit()
    exit(1)

projects = []

try:
    print('Locating project cards...')
    # Find all project cards (update selector if needed)
    cards = driver.find_elements(By.CSS_SELECTOR, 'div.card, .project-list-card, .mat-card')
    print(f'Found {len(cards)} project cards.')
    for idx in range(len(cards)):
        try:
            # Re-locate all cards after each navigation to avoid stale elements
            cards = driver.find_elements(By.CSS_SELECTOR, 'div.card, .project-list-card, .mat-card, .col-md-2')
            card = cards[idx]
            view_more = card.find_element(By.XPATH, ".//a[contains(text(), 'View More') or contains(text(), 'Details')]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", view_more)
            view_more.click()
            # Wait for the details page to load (wait for a known field)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Project Name') or contains(text(), 'Registration') or contains(text(), 'Promoter') or contains(text(), 'Builder') or contains(text(), 'Address') or contains(text(), 'Locality') or contains(text(), 'Unit') or contains(text(), 'Price') or contains(text(), 'Completion') or contains(text(), 'Status') or contains(text(), 'Start Date') or contains(text(), 'End Date') or contains(text(), 'Available') or contains(text(), 'Sold') or contains(text(), 'Type') or contains(text(), 'RERA') or contains(text(), 'Reg No') or contains(text(), 'Date') or contains(text(), 'Status') or contains(text(), 'Type') or contains(text(), 'Unit') or contains(text(), 'Price') or contains(text(), 'Promoter') or contains(text(), 'Builder') or contains(text(), 'Address') or contains(text(), 'Locality') or contains(text(), 'Unit') or contains(text(), 'Price') or contains(text(), 'Completion') or contains(text(), 'Status') or contains(text(), 'Start Date') or contains(text(), 'End Date') or contains(text(), 'Available') or contains(text(), 'Sold') or contains(text(), 'Type') or contains(text(), 'RERA') or contains(text(), 'Reg No') or contains(text(), 'Date') or contains(text(), 'Status') or contains(text(), 'Type') or contains(text(), 'Unit') or contains(text(), 'Price')]")))
            # Extract all required fields from the details page
            project = {}
            def extract_detail(label_keywords):
                for kw in label_keywords:
                    try:
                        el = driver.find_element(By.XPATH, f"//*[contains(text(), '{kw}')]")
                        txt = el.text
                        # Try to get the value after ':'
                        if ':' in txt:
                            return txt.split(':', 1)[-1].strip()
                        else:
                            return txt.strip()
                    except Exception:
                        continue
                return ''
            project['Project Name'] = extract_detail(['Project Name'])
            project['RERA Reg Number'] = extract_detail(['Registration No', 'RERA No', 'Reg No'])
            project['Promoter'] = extract_detail(['Promoter', 'Builder'])
            project['Address'] = extract_detail(['Address'])
            project['Locality'] = extract_detail(['Locality', 'Location'])
            project['Unit Types'] = extract_detail(['Unit Type', 'Type of Unit'])
            project['Available Units'] = extract_detail(['Available Unit', 'Available Units'])
            project['Sold Units'] = extract_detail(['Sold Unit', 'Sold Units'])
            project['Price per Unit'] = extract_detail(['Price'])
            project['Registration Date'] = extract_detail(['Registration Date', 'Start Date'])
            project['Completion Status'] = extract_detail(['Status', 'Completion'])
            projects.append(project)
            print(f'Extracted: {project}')
            # Go back to the project list
            driver.back()
            # Wait for cards to reload
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'View More') or contains(text(), 'Details')]")))
            time.sleep(1)
        except Exception as e:
            print(f'Error extracting project card #{idx+1}:', e)
            traceback.print_exc()

    print(f'Extracted {len(projects)} projects.')
except Exception as e:
    print('Error extracting project cards:', e)
    traceback.print_exc()

# Export to CSV
if projects:
    df = pd.DataFrame(projects)
    append_unique_by_regno(df, 'ahmedabad_projects.csv')
    print('Saved/updated ahmedabad_projects.csv')
else:
    print('No projects found.')

driver.quit()
