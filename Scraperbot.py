import requests
from bs4 import BeautifulSoup
import os
import json
import time
import random

# --- 1. CONFIGURATION ---

# IMPORTANT: You must update the CSS selectors below based on your inspection
# This is a general example for Lidl UK Weekly Offers (might not work perfectly)
STORE_TARGETS = [
    {
        'store': 'Lidl UK',
        'url': 'https://www.lidl.co.uk/c/all-offers/c10000',
        'product_container': 'div.product-grid-box__details',
        'product_name': 'h3.product-title',
        'product_price': 'div.pricebox__price',
    },
    # Add more stores here (e.g., Aldi, SuperValu) with their specific selectors
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:99.0) Gecko/20100101 Firefox/99.0'
]

# Load secure Telegram credentials from GitHub Secrets
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# File path for saving previous deals on the GitHub runner
HISTORY_FILE = 'previous_deals.json'


# --- 2. CORE FUNCTIONS ---

def send_telegram_alert(message):
    """Sends a message via the Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        print("ERROR: Telegram credentials not set. Cannot send alert.")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print(f"Telegram message sent successfully! Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"ERROR sending Telegram message: {e}")
        return False


def scrape_site(target):
    """Fetches and parses deals from a single store URL."""
    print(f"--- Scraping {target['store']} ---")
    
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    
    try:
        response = requests.get(target['url'], headers=headers, timeout=15)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Request failed for {target['store']}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # List to hold the current deals for this store
    current_deals = []
    
    # Use the product_container to find all deal boxes
    containers = soup.select(target['product_container'])

    for container in containers:
        try:
            # Extract name and price using specific selectors
            name_tag = container.select_one(target['product_name'])
            price_tag = container.select_one(target['product_price'])
            
            if name_tag and price_tag:
                name = name_tag.get_text(strip=True)
                price = price_tag.get_text(strip=True).replace('\n', ' ').strip()
                
                # Create a unique ID for comparison
                deal_id = f"{target['store']}-{name}-{price}"
                
                current_deals.append({
                    'id': deal_id,
                    'store': target['store'],
                    'name': name,
                    'price': price,
                    'link': target['url'] # Basic link to offers page
                })
        except Exception as e:
            print(f"Error parsing item in {target['store']}: {e}")
            continue

    return current_deals

def load_previous_deals():
    """Loads previous deals from the history file."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            print(f"Loaded {len(f.read())} bytes from previous deals file.")
            f.seek(0) # Reset file pointer
            return set(json.load(f))
    return set()

def save_current_deals(deals):
    """Saves the IDs of the current deals to the history file."""
    with open(HISTORY_FILE, 'w') as f:
        # Save only the unique IDs for comparison
        deal_ids = [deal['id'] for deal in deals]
        json.dump(deal_ids, f)
    print(f"Saved {len(deal_ids)} deal IDs for next run.")


# --- 3. MAIN EXECUTION ---

if __name__ == "__main__":
    
    all_current_deals = []
    
    # 1. Load previous deals for comparison
    previous_deal_ids = load_previous_deals()
    
    # 2. Scrape all targets
    for target in STORE_TARGETS:
        deals = scrape_site(target)
        all_current_deals.extend(deals)
        
        # RESPECTFUL DELAY: Wait between sites
        time.sleep(random.randint(5, 10))
        
    # 3. Find New Deals
    new_deals = []
    for deal in all_current_deals:
        if deal['id'] not in previous_deal_ids:
            new_deals.append(deal)

    # 4. Prepare and Send Alert
    
    if new_deals:
        print(f"Found {len(new_deals)} new deals!")
        
        # Build the Telegram Message
        message = "*🚨 New Supermarket Deals Alert! 🚨*\n\n"
        
        for deal in new_deals:
            message += f"🛒 *{deal['store']}*\n"
            message += f" {deal['name']}\n"
            message += f" *{deal['price']}* (on offers page)\n"
            message += "--- \n"
            
        message += f"\n_Total new deals found: {len(new_deals)}_"
        
        send_telegram_alert(message)
    else:
        print("No new deals found since the last run.")
        send_telegram_alert("✅ *Daily Deal Check Complete*:\n_No significant new deals found today._")

    # 5. Save current deals for the next comparison
    save_current_deals(all_current_deals)
      
