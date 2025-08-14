# Multi-Project Real Estate Scraper for Gujarat RERA (All Ahmedabad Projects)
# Requirements: selenium, pandas, openpyxl
# Usage: python scrape_all_ahmedabad_projects.py

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import traceback
import re

# Setup Selenium
options = webdriver.ChromeOptions()
options.add_argument('--start-maximized')
# Keep headless mode OFF for debugging
# options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.183 Safari/537.36')
service = Service('H:\\DataAnalytics_project\\real_estate_analysis\\chromedriver-win64\\chromedriver.exe')
driver = webdriver.Chrome(service=service, options=options)

# Set longer page load timeout
print('Setting page load timeout to 180 seconds...')
driver.set_page_load_timeout(180)

wait = WebDriverWait(driver, 20)
actions = ActionChains(driver)

print('Starting multi-project scraper for all Ahmedabad projects...')

# Try loading the base URL first, then /#/home
try:
    print('Loading base Gujarat RERA URL...')
    driver.get('https://gujrera.gujarat.gov.in/')
    print('Base URL loaded. Now loading /#/home ...')
    driver.get('https://gujrera.gujarat.gov.in/#/home')
    print('Home URL loaded.')
    print('Current URL:', driver.current_url)
except Exception as e:
    print('Error loading page:', e)

try:
    print('Waiting for home page to load...')
    search_bar = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@placeholder, "Project, Agent, Promoter")]')))
    print('Typing "district" in search bar and pressing Enter...')
    search_bar.clear()
    search_bar.send_keys('district')
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

    # Scroll down slightly to bring cards into view
    driver.execute_script('window.scrollBy(0, 250);')
    time.sleep(1)

    # Initialize list to store all projects data and track processed projects
    all_projects_data = []
    processed_projects = set()  # Track processed projects to avoid duplicates
    project_count = 0

    # Ensure all projects are loaded by scrolling to bottom and checking for pagination
    print('Loading all projects by scrolling and checking pagination...')
    
    # Scroll to load all projects
    last_project_count = 0
    scroll_attempts = 0
    max_scroll_attempts = 15  # Increased from 10 to 15
    
    while scroll_attempts < max_scroll_attempts:
        # Scroll down to load more projects
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        time.sleep(5)  # Increased from 3 to 5 seconds
        
        # Also try scrolling in smaller increments to trigger lazy loading
        for i in range(3):
            driver.execute_script(f'window.scrollBy(0, {500 * (i + 1)});')
            time.sleep(2)
        
        # Check current number of projects
        view_more_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.vmore.mb-2')
        current_project_count = len(view_more_buttons)
        
        print(f'Scroll attempt {scroll_attempts + 1}: Found {current_project_count} projects')
        
        # If no new projects loaded, try clicking pagination buttons
        try:
            # Look for various types of pagination buttons
            pagination_selectors = [
                "//button[contains(text(), 'Load More') or contains(text(), 'Show More') or contains(text(), 'Next')]",
                "//a[contains(text(), 'Load More') or contains(text(), 'Show More') or contains(text(), 'Next')]",
                "//button[contains(@class, 'load-more') or contains(@class, 'show-more')]",
                "//a[contains(@class, 'load-more') or contains(@class, 'show-more')]",
                "//button[text()='2' or text()='3' or text()='4' or text()='5']",  # Numeric pagination
                "//a[text()='2' or text()='3' or text()='4' or text()='5']",
                "//li[contains(@class, 'page-item')]//a[not(contains(text(), 'Previous'))]"
            ]
            
            button_clicked = False
            for selector in pagination_selectors:
                if button_clicked:
                    break
                    
                buttons = driver.find_elements(By.XPATH, selector)
                for btn in buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(2)
                            btn.click()
                            print(f'Clicked pagination button: {btn.text}')
                            time.sleep(5)  # Wait longer after clicking pagination
                            button_clicked = True
                            break
                    except Exception as btn_e:
                        continue
                        
        except Exception as e:
            print(f'No pagination buttons found: {e}')
        
        # Check if we found new projects
        if current_project_count == last_project_count:
            scroll_attempts += 1
        else:
            scroll_attempts = 0  # Reset if we found new projects
            
        last_project_count = current_project_count
        
        # Continue until we have all expected projects or exhaust attempts
        # Don't break early - let it try to find all projects
        if current_project_count >= 40:  # Only break if we have significantly more than expected
            print(f'Found {current_project_count} projects, which is more than expected. Stopping search.')
            break
    
    # Final count with multiple selectors to ensure we find all projects
    selectors_to_try = [
        'a.vmore.mb-2',
        'a.vmore',
        'a[href*="project-details"]',
        'a[href*="view-more"]',
        '.project-card a',
        '.card a.vmore'
    ]
    
    max_projects_found = 0
    best_selector = None
    
    for selector in selectors_to_try:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, selector)
            if len(buttons) > max_projects_found:
                max_projects_found = len(buttons)
                best_selector = selector
                print(f'Selector "{selector}" found {len(buttons)} projects')
        except Exception as e:
            print(f'Selector "{selector}" failed: {e}')
    
    # Use the best selector
    view_more_buttons = driver.find_elements(By.CSS_SELECTOR, best_selector or 'a.vmore.mb-2')
    total_projects = len(view_more_buttons)
    print(f'Final count using selector "{best_selector}": Found {total_projects} projects to process')
    
    # Scroll back to top
    driver.execute_script('window.scrollTo(0, 0);')
    time.sleep(2)

    # Process each project
    for project_index in range(total_projects):
        try:
            print(f'\n=== Processing Project {project_index + 1} of {total_projects} ===')
            
            # Navigate back to project listing if not first project
            if project_index > 0:
                print('Navigating back to project listing...')
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
                
                # Look for "Project Profile" link in header
                project_profile_selectors = [
                    "//a[contains(text(), 'Project Profile')]",
                    "//a[contains(text(), 'Project')]",
                    "//button[contains(text(), 'Project Profile')]",
                    "//span[contains(text(), 'Project Profile')]/parent::*"
                ]
                
                project_profile_clicked = False
                for selector in project_profile_selectors:
                    try:
                        elements = driver.find_elements(By.XPATH, selector)
                        for element in elements:
                            if element.is_displayed() and element.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(1)
                                element.click()
                                print('Clicked on Project Profile link')
                                project_profile_clicked = True
                                break
                        if project_profile_clicked:
                            break
                    except Exception:
                        continue
                
                if project_profile_clicked:
                    time.sleep(3)
                    print('Successfully navigated back to project listing')
                    
                    # Reapply Ahmedabad filter using same method as initial setup
                    print('Reapplying Ahmedabad district filter...')
                    try:
                        # Type 'district' in search bar and press Enter
                        search_bar = wait.until(EC.visibility_of_element_located((By.XPATH, '//input[contains(@placeholder, "Project, Agent, Promoter")]')))
                        search_bar.clear()
                        search_bar.send_keys('district')
                        search_bar.send_keys(u'\ue007')  # Press Enter key
                        time.sleep(3)
                        
                        # Click filter panel
                        filter_panel_link = wait.until(EC.element_to_be_clickable((By.ID, 'clickForFilter')))
                        filter_panel_link.click()
                        time.sleep(2)
                        
                        # Select Ahmedabad district
                        district_dropdown = WebDriverWait(driver, 30).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'select[formcontrolname="distName"]'))
                        )
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", district_dropdown)
                        actions.move_to_element(district_dropdown).click().perform()
                        time.sleep(1)
                        select = Select(district_dropdown)
                        select.select_by_visible_text('Ahmedabad')
                        time.sleep(1)
                        
                        # Click Apply button
                        apply_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.fBtn.applyButtonCl')))
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_btn)
                        time.sleep(0.5)
                        apply_btn.click()
                        print('Applied filter. Waiting for results...')
                        time.sleep(8)  # Increased timeout for filter results
                    except Exception as filter_e:
                        print(f'Error reapplying filter: {filter_e}')
                        # Try to continue anyway
                        time.sleep(3)
                else:
                    print('Could not navigate back to project listing')
                    continue
            
            # Find and extract data from project card before clicking View More
            try:
                driver.execute_script('window.scrollBy(0, 250);')
                time.sleep(2)
                
                # Re-find all View More buttons and their parent project cards
                view_more_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.vmore.mb-2')
                
                if project_index >= len(view_more_buttons):
                    print(f'Project {project_index + 1} not found. Stopping.')
                    break
                    
                view_more_btn = view_more_buttons[project_index]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", view_more_btn)
                
                # Extract data from project card before clicking using the correct HTML structure
                card_data = {'Total Units': '', 'Available Units': '', 'Total No. of Towers/Blocks': ''}
                try:
                    # Find the parent project card
                    project_card = view_more_btn.find_element(By.XPATH, "./ancestor::div[contains(@class, 'card') or contains(@class, 'project')]")
                    
                    # Extract Available Units from <strong> tag following "Available Units" text
                    try:
                        available_units_elements = project_card.find_elements(By.XPATH, ".//li[contains(., 'Available Units')]//strong")
                        if available_units_elements:
                            card_data['Available Units'] = available_units_elements[0].text.strip()
                            print(f"[DEBUG] Found Available Units in card: {card_data['Available Units']}")
                        else:
                            # Fallback: look for pattern in text
                            card_text = project_card.text
                            available_match = re.search(r'available units[^\d]*?(\d+)', card_text, re.IGNORECASE)
                            if available_match:
                                card_data['Available Units'] = available_match.group(1)
                                print(f"[DEBUG] Found Available Units via regex: {card_data['Available Units']}")
                    except Exception as e:
                        print(f"[DEBUG] Error extracting Available Units from card: {e}")
                    
                    # Extract Total No. of Towers/Blocks from <strong> tag
                    try:
                        towers_elements = project_card.find_elements(By.XPATH, ".//li[contains(., 'Total No. of Towers/Blocks')]//strong")
                        if towers_elements:
                            card_data['Total No. of Towers/Blocks'] = towers_elements[0].text.strip()
                            print(f"[DEBUG] Found Towers/Blocks in card: {card_data['Total No. of Towers/Blocks']}")
                        else:
                            # Fallback: look for pattern in text
                            card_text = project_card.text
                            towers_match = re.search(r'(?:total no\. of towers/blocks|towers?|blocks?)[^\d]*?(\d+)', card_text, re.IGNORECASE)
                            if towers_match:
                                card_data['Total No. of Towers/Blocks'] = towers_match.group(1)
                                print(f"[DEBUG] Found Towers/Blocks via regex: {card_data['Total No. of Towers/Blocks']}")
                    except Exception as e:
                        print(f"[DEBUG] Error extracting Towers/Blocks from card: {e}")
                    
                    # Extract Total Units from <strong> tag
                    try:
                        total_units_elements = project_card.find_elements(By.XPATH, ".//li[contains(., 'Total Units')]//strong")
                        if total_units_elements:
                            card_data['Total Units'] = total_units_elements[0].text.strip()
                            print(f"[DEBUG] Found Total Units in card: {card_data['Total Units']}")
                        else:
                            # Fallback: look for pattern in text
                            card_text = project_card.text
                            total_match = re.search(r'total units[^\d]*?(\d+)', card_text, re.IGNORECASE)
                            if total_match:
                                card_data['Total Units'] = total_match.group(1)
                                print(f"[DEBUG] Found Total Units via regex: {card_data['Total Units']}")
                    except Exception as e:
                        print(f"[DEBUG] Error extracting Total Units from card: {e}")
                        
                except Exception as card_e:
                    print(f"[DEBUG] Error extracting from project card: {card_e}")
                
                print(f'Clicking View More for project {project_index + 1}...')
                view_more_btn.click()
                time.sleep(3)
                
                # Wait for details page to load
                wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Project Name') or contains(text(), 'Registration') or contains(text(), 'RERA')]")))
                print('Project details page loaded')
                
            except Exception as e:
                print(f'Error accessing project {project_index + 1}: {e}')
                continue

            # Scroll through the details page to load all sections
            print('Scrolling through details page...')
            last_height = driver.execute_script('return document.body.scrollHeight')
            for y in range(0, last_height, 400):
                driver.execute_script(f'window.scrollTo(0, {y});')
                time.sleep(0.5)
            time.sleep(1)

            # Initialize project data dictionary
            project_data = {
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
            }
            type_details_rows = []

            # Extract all project fields (using same logic as original script)
            def extract_field(field_name, marker):
                """Helper function to extract field values"""
                td_elems = driver.find_elements(By.XPATH, f"//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{field_name.lower()}')]")
                for td in td_elems:
                    try:
                        full_text = td.text.strip()
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
                                return value
                    except Exception:
                        continue
                return ''

            # Extract basic project information
            project_data['Project Name'] = extract_field('project name', 'Project Name:-')
            project_data['RERA Reg. No.'] = extract_field('gujrera reg. no.', 'GUJRERA Reg. No.:-')
            
            # Create unique identifier for duplicate detection
            project_identifier = f"{project_data['Project Name']}|{project_data['RERA Reg. No.']}"
            
            # Check for duplicates - skip if already processed
            if project_identifier in processed_projects:
                print(f"[SKIP] Project '{project_data['Project Name']}' (RERA: {project_data['RERA Reg. No.']}) already processed. Skipping duplicate.")
                continue
            
            # Add to processed set
            processed_projects.add(project_identifier)
            project_data['Project Address'] = extract_field('project address', 'Project Address:-')
            project_data['Project Type'] = extract_field('project type', 'Project Type:-')
            project_data['About Property'] = extract_field('about property', 'About Property:-')
            project_data['Project Start Date'] = extract_field('project start date', 'Project Start Date:-')
            project_data['Project End Date'] = extract_field('project end date', 'Project End Date:-')
            project_data['Project Land Area'] = extract_field('project land area', 'Project Land Area:-')
            project_data['Total Open Area'] = extract_field('total open area', 'Total Open Area:-')
            project_data['Total Covered Area'] = extract_field('total covered area', 'Total Covered Area:-')
            project_data['Carpet Area of Units (Range)'] = extract_field('carpet area of units (range)', 'Carpet Area of Units (Range):-')
            project_data['Plan Passing Authority'] = extract_field('plan passing authority', 'Plan Passing Authority:-')

            # Extract Amenities
            amenities = []
            try:
                amenity_labels = driver.find_elements(By.XPATH, "//strong[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'common amenities')]")
                for label in amenity_labels:
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
                        break
            except Exception:
                pass
            if amenities:
                project_data['Amenities'] = ', '.join(amenities)

            # Use card data first, then try detailed page extraction
            if card_data.get('Total Units'):
                project_data['Total Units'] = card_data['Total Units']
                print(f"[DEBUG] Using Total Units from card: {card_data['Total Units']}")
            else:
                # Extract Total Units with comprehensive approach from detailed page
                try:
                    print("[DEBUG] Starting Total Units extraction from detailed page...")
                    all_elements = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'total units')]")
                    print(f"[DEBUG] Found {len(all_elements)} elements containing 'total units'")
                    
                    for element in all_elements:
                        try:
                            text = element.text.strip()
                            print(f"[DEBUG] Total Units element text: '{text}'")
                            numbers = re.findall(r'\d+', text)
                            if numbers:
                                project_data['Total Units'] = numbers[0]
                                print(f"[DEBUG] Found Total Units in same element: {numbers[0]}")
                                break
                                
                            # Try following siblings
                            try:
                                following_elements = element.find_elements(By.XPATH, "./following-sibling::*[position()<=3]")
                                for sibling in following_elements:
                                    sibling_text = sibling.text.strip()
                                    sibling_numbers = re.findall(r'\d+', sibling_text)
                                    if sibling_numbers:
                                        project_data['Total Units'] = sibling_numbers[0]
                                        print(f"[DEBUG] Found Total Units in following sibling: {sibling_numbers[0]}")
                                        break
                                if project_data['Total Units']:
                                    break
                            except Exception:
                                pass
                                
                            # Try parent element
                            try:
                                parent = element.find_element(By.XPATH, "./parent::*")
                                parent_text = parent.text.strip()
                                parent_numbers = re.findall(r'\d+', parent_text)
                                if parent_numbers:
                                    for num in parent_numbers:
                                        if num not in text:
                                            project_data['Total Units'] = num
                                            print(f"[DEBUG] Found Total Units in parent element: {num}")
                                            break
                                if project_data['Total Units']:
                                    break
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"[DEBUG] Error processing Total Units element: {e}")
                            continue
                            
                    if not project_data['Total Units']:
                        print("[DEBUG] Total Units not found with standard approach, trying page source...")
                        page_text = driver.page_source.lower()
                        if 'total units' in page_text:
                            pattern = r'total units[^\d]*?(\d+)'
                            matches = re.findall(pattern, page_text, re.IGNORECASE)
                            if matches:
                                project_data['Total Units'] = matches[0]
                                print(f"[DEBUG] Found Total Units from page source: {matches[0]}")
                                
                except Exception as e:
                    print(f"[DEBUG] Error extracting Total Units: {e}")
            
            # Use card data first for Available Units
            if card_data.get('Available Units'):
                project_data['Available Units'] = card_data['Available Units']
                print(f"[DEBUG] Using Available Units from card: {card_data['Available Units']}")
            else:
                # Extract Available Units with comprehensive approach from detailed page
                try:
                    print("[DEBUG] Starting Available Units extraction from detailed page...")
                    all_elements = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'available units')]")
                    print(f"[DEBUG] Found {len(all_elements)} elements containing 'available units'")
                    
                    for element in all_elements:
                        try:
                            text = element.text.strip()
                            print(f"[DEBUG] Available Units element text: '{text}'")
                            numbers = re.findall(r'\d+', text)
                            if numbers:
                                project_data['Available Units'] = numbers[0]
                                print(f"[DEBUG] Found Available Units in same element: {numbers[0]}")
                                break
                                
                            # Try following siblings
                            try:
                                following_elements = element.find_elements(By.XPATH, "./following-sibling::*[position()<=3]")
                                for sibling in following_elements:
                                    sibling_text = sibling.text.strip()
                                    sibling_numbers = re.findall(r'\d+', sibling_text)
                                    if sibling_numbers:
                                        project_data['Available Units'] = sibling_numbers[0]
                                        print(f"[DEBUG] Found Available Units in following sibling: {sibling_numbers[0]}")
                                        break
                                if project_data['Available Units']:
                                    break
                            except Exception:
                                pass
                                
                            # Try parent element
                            try:
                                parent = element.find_element(By.XPATH, "./parent::*")
                                parent_text = parent.text.strip()
                                parent_numbers = re.findall(r'\d+', parent_text)
                                if parent_numbers:
                                    for num in parent_numbers:
                                        if num not in text:
                                            project_data['Available Units'] = num
                                            print(f"[DEBUG] Found Available Units in parent element: {num}")
                                            break
                                if project_data['Available Units']:
                                    break
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"[DEBUG] Error processing Available Units element: {e}")
                            continue
                            
                    if not project_data['Available Units']:
                        print("[DEBUG] Available Units not found with standard approach, trying page source...")
                        page_text = driver.page_source.lower()
                        if 'available units' in page_text:
                            pattern = r'available units[^\d]*?(\d+)'
                            matches = re.findall(pattern, page_text, re.IGNORECASE)
                            if matches:
                                project_data['Available Units'] = matches[0]
                                print(f"[DEBUG] Found Available Units from page source: {matches[0]}")
                                
                except Exception as e:
                    print(f"[DEBUG] Error extracting Available Units: {e}")
            
            # Use card data first for Towers/Blocks
            if card_data.get('Total No. of Towers/Blocks'):
                project_data['Total No. of Towers/Blocks'] = card_data['Total No. of Towers/Blocks']
                print(f"[DEBUG] Using Towers/Blocks from card: {card_data['Total No. of Towers/Blocks']}")
            else:
                # Extract Total No. of Towers/Blocks with comprehensive approach from detailed page
                try:
                    print("[DEBUG] Starting Total No. of Towers/Blocks extraction from detailed page...")
                    search_terms = ['towers/blocks', 'total no. of towers/blocks', 'towers', 'blocks']
                    
                    for term in search_terms:
                        all_elements = driver.find_elements(By.XPATH, f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{term}')]")
                        print(f"[DEBUG] Found {len(all_elements)} elements containing '{term}'")
                        
                        for element in all_elements:
                            try:
                                text = element.text.strip()
                                print(f"[DEBUG] Towers/Blocks element text: '{text}'")
                                numbers = re.findall(r'\d+', text)
                                if numbers:
                                    project_data['Total No. of Towers/Blocks'] = numbers[0]
                                    print(f"[DEBUG] Found Total No. of Towers/Blocks in same element: {numbers[0]}")
                                    break
                                    
                                # Try following siblings
                                try:
                                    following_elements = element.find_elements(By.XPATH, "./following-sibling::*[position()<=3]")
                                    for sibling in following_elements:
                                        sibling_text = sibling.text.strip()
                                        sibling_numbers = re.findall(r'\d+', sibling_text)
                                        if sibling_numbers:
                                            project_data['Total No. of Towers/Blocks'] = sibling_numbers[0]
                                            print(f"[DEBUG] Found Total No. of Towers/Blocks in following sibling: {sibling_numbers[0]}")
                                            break
                                    if project_data['Total No. of Towers/Blocks']:
                                        break
                                except Exception:
                                    pass
                                    
                                # Try parent element
                                try:
                                    parent = element.find_element(By.XPATH, "./parent::*")
                                    parent_text = parent.text.strip()
                                    parent_numbers = re.findall(r'\d+', parent_text)
                                    if parent_numbers:
                                        for num in parent_numbers:
                                            if num not in text:
                                                project_data['Total No. of Towers/Blocks'] = num
                                                print(f"[DEBUG] Found Total No. of Towers/Blocks in parent element: {num}")
                                                break
                                    if project_data['Total No. of Towers/Blocks']:
                                        break
                                except Exception:
                                    pass
                            except Exception as e:
                                print(f"[DEBUG] Error processing Towers/Blocks element: {e}")
                                continue
                        
                        if project_data['Total No. of Towers/Blocks']:
                            break
                            
                    if not project_data['Total No. of Towers/Blocks']:
                        print("[DEBUG] Towers/Blocks not found with standard approach, trying page source...")
                        page_text = driver.page_source.lower()
                        for term in search_terms:
                            if term in page_text:
                                pattern = f'{term}[^\d]*?(\d+)'
                                matches = re.findall(pattern, page_text, re.IGNORECASE)
                                if matches:
                                    project_data['Total No. of Towers/Blocks'] = matches[0]
                                    print(f"[DEBUG] Found Total No. of Towers/Blocks from page source: {matches[0]}")
                                    break
                    
                except Exception as e:
                    print(f"[DEBUG] Error extracting Total No. of Towers/Blocks: {e}")

            # Extract Promoter information
            project_data['Promoter Name'] = extract_field('promoter name', 'Promoter Name:-')
            project_data['Promoter Type'] = extract_field('promoter type', 'Promoter Type:-')
            project_data['Office Address'] = extract_field('office address', 'Office Address:-')

            # Extract Partners
            partners = []
            try:
                td_elems = driver.find_elements(By.XPATH, "//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'partners')]")
                for td in td_elems:
                    try:
                        full_text = td.text.strip()
                        if 'Partners:-' in full_text:
                            lines = full_text.split('\n')
                            for line in lines:
                                if line.strip() and line.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                                    partner = line.strip()[2:].strip()
                                    if partner:
                                        partners.append(partner)
                    except Exception:
                        continue
            except Exception:
                pass

            # Add partner columns dynamically
            for i, partner in enumerate(partners, 1):
                project_data[f'Partner {i}'] = partner

            # Extract Type Details table
            try:
                type_details_found = False
                tables = driver.find_elements(By.XPATH, "//table")
                for table in tables:
                    headers = table.find_elements(By.XPATH, ".//th")
                    header_texts = [th.text.strip().lower() for th in headers]
                    if ('unit type' in header_texts and 'block' in header_texts and 'total units' in header_texts):
                        rows = table.find_elements(By.XPATH, ".//tr")
                        if len(rows) >= 2:
                            headers = [th.text.strip() for th in rows[0].find_elements(By.XPATH, ".//th")]
                            for row in rows[1:]:
                                cells = row.find_elements(By.XPATH, ".//td")
                                if len(cells) == len(headers):
                                    row_dict = {headers[i]: cells[i].text.strip() for i in range(len(headers))}
                                    if any(row_dict.values()):
                                        type_details_rows.append(row_dict)
                            type_details_found = True
                            break
            except Exception as e:
                print(f'Error extracting Type Details: {e}')

            # Combine Type Details into single row
            combined_row = project_data.copy()
            if type_details_rows:
                type_keys = set()
                for row in type_details_rows:
                    type_keys.update(row.keys())
                for k in type_keys:
                    values = [row.get(k, '') for row in type_details_rows if row.get(k, '')]
                    if values:
                        combined_row[k] = '; '.join(values)

            # Add current project to all_projects_data list
            all_projects_data.append(combined_row)
            project_count += 1
            
            print(f'✓ Successfully processed project {project_count}: {combined_row.get("Project Name", "Unknown")}')
            
            # Save progress after every 5 projects
            if project_count % 5 == 0:
                df_progress = pd.DataFrame(all_projects_data)
                df_progress.to_csv('ahmedabad_all_projects_progress.csv', index=False)
                print(f'Progress saved. {project_count} projects completed.')
                
        except Exception as e:
            print(f'Error processing project {project_index + 1}: {e}')
            traceback.print_exc()
            continue

    # Save final results
    print(f'\n=== SCRAPING COMPLETED ===')
    print(f'Total projects processed: {len(all_projects_data)}')

    if all_projects_data:
        # Save final CSV with all projects
        df_final = pd.DataFrame(all_projects_data)
        df_final.to_csv('ahmedabad_all_projects_final.csv', index=False)
        print(f'✓ All {len(all_projects_data)} projects saved to ahmedabad_all_projects_final.csv')
        
        # Print summary
        project_names = [proj.get('Project Name', 'Unknown') for proj in all_projects_data]
        print('\nProjects processed:')
        for i, name in enumerate(project_names, 1):
            print(f'{i}. {name}')
    else:
        print('No projects were successfully processed.')

except KeyboardInterrupt:
    print('\nScript interrupted by user. Saving current progress...')
    if all_projects_data:
        df_interrupted = pd.DataFrame(all_projects_data)
        df_interrupted.to_csv('ahmedabad_all_projects_interrupted.csv', index=False)
        print(f'Progress saved. {len(all_projects_data)} projects completed before interruption.')

except Exception as e:
    print(f'\nUnexpected error: {e}')
    traceback.print_exc()
    if all_projects_data:
        df_error = pd.DataFrame(all_projects_data)
        df_error.to_csv('ahmedabad_all_projects_error.csv', index=False)
        print(f'Progress saved. {len(all_projects_data)} projects completed before error.')

finally:
    driver.quit()
    print('Browser closed. Multi-project scraping completed!')
