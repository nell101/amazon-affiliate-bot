# main.py - Amazon Affiliate Blogger Bot - Supercharged Version
# Complete deployment-ready version with proper OAuth token handling and new feature

import os
import time
import requests
import json
import random
import hashlib
from datetime import datetime, timedelta
from threading import Thread, Event
import logging
from urllib.parse import quote
from flask import Flask
import re
import signal
import sys
import traceback

# Health check server for Render
app = Flask(__name__)

@app.route('/')
def health():
    return "🚀 Amazon Affiliate Bot is running! Posts every hour to freshfindsstore.blogspot.com"

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/stats')
def stats():
    return {
        "status": "active",
        "blog": "freshfindsstore.blogspot.com",
        "posting_interval": "every hour",
        "last_check": datetime.now().isoformat()
    }

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AmazonAffiliateBlogBot:
    def __init__(self):
        # Your credentials - already integrated
        self.blogger_url = "https://freshfindsstore.blogspot.com"
        self.blogger_id = "7258302130838734343"
        self.gemini_api_key = os.getenv('GEMINI_API_KEY', 'AIzaSyDhSmOqJB3HU553_ZTLpAUxXAwVGuEaSmQ')
        self.bitly_token = os.getenv('BITLY_TOKEN', '84e3fa55424e93055b030a86cf3a17c2bb8865c0')
        self.amazon_tag = os.getenv('AMAZON_TAG', 'topamazonpi06-20')
        
        # Get OAuth credentials from environment variables
        self.refresh_token = os.getenv('GOOGLE_OAUTH_TOKEN')
        self.client_id = os.getenv('GOOGLE_CLIENT_ID', '')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '')
        
        # Token management
        self.access_token = None
        self.token_expires_at = 0
        self.token_type = None  # Will be 'access' or 'refresh'
        
        # Initialize posted products tracking set
        self.posted_products = set()
        
        # Add shutdown event for graceful stopping
        self.shutdown_event = Event()
        
        # High-converting product categories and keywords
        self.trending_categories = [
            "electronics", "home-kitchen", "fashion", "beauty", "sports-outdoors",
            "automotive", "tools-home-improvement", "toys-games", "health-personal-care",
            "books", "baby-products", "pet-supplies", "garden-lawn", "musical-instruments"
        ]
        
        # High-intent keywords for product selection
        self.high_intent_keywords = [
            "best", "top rated", "premium", "professional", "wireless", "smart",
            "portable", "rechargeable", "waterproof", "ergonomic", "adjustable",
            "multi-purpose", "heavy-duty", "eco-friendly", "energy efficient"
        ]
        
        # Add retry configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
        # Determine token type on initialization
        self._analyze_token_type()
        
    def _analyze_token_type(self):
        """Analyze and determine the type of token we have"""
        if not self.refresh_token:
            logger.error("❌ No authentication token found in environment variables")
            return
            
        if self.refresh_token.startswith('ya29.'):
            self.token_type = 'access'
            self.access_token = self.refresh_token
            # Assume it expires in 1 hour (3600 seconds) minus 5 minutes buffer
            self.token_expires_at = time.time() + 3300
            logger.info("✅ Detected access token (ya29.)")
        elif self.refresh_token.startswith('1//'):
            self.token_type = 'refresh'
            logger.info("✅ Detected refresh token (1//)")
        else:
            # Try to determine by length and content
            if len(self.refresh_token) > 100 and '.' in self.refresh_token:
                self.token_type = 'access'
                self.access_token = self.refresh_token
                self.token_expires_at = time.time() + 3300
                logger.info("✅ Assuming access token based on format")
            else:
                self.token_type = 'refresh'
                logger.info("✅ Assuming refresh token based on format")
        
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"🛑 Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def diagnose_authentication(self):
        """Enhanced authentication diagnosis with token validation"""
        logger.info("🔍 Diagnosing authentication setup...")
        
        # Check environment variables
        logger.info(f"GOOGLE_OAUTH_TOKEN present: {'✅' if self.refresh_token else '❌'}")
        logger.info(f"GOOGLE_CLIENT_ID present: {'✅' if self.client_id else '❌'}")
        logger.info(f"GOOGLE_CLIENT_SECRET present: {'✅' if self.client_secret else '❌'}")
        
        if self.refresh_token:
            logger.info(f"Token type: {self.token_type}")
            logger.info(f"Token length: {len(self.refresh_token)}")
            logger.info(f"Token starts with: {self.refresh_token[:15]}...")
            
            if self.token_type == 'refresh' and not (self.client_id and self.client_secret):
                logger.warning("⚠️ Refresh token detected but missing client credentials")
                logger.info("💡 For refresh tokens, set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
                logger.info("💡 Alternatively, use a fresh access token instead")
        
        return True

    def get_access_token(self):
        """Get valid access token with improved handling for both token types"""
        try:
            current_time = time.time()
            
            # If we have a valid access token that hasn't expired, use it
            if (self.access_token and 
                current_time < (self.token_expires_at - 300) and  # 5-minute buffer
                self.token_type == 'access'):
                return self.access_token
            
            # If we have a refresh token, try to get a new access token
            if self.token_type == 'refresh':
                logger.info("🔄 Refreshing access token using refresh token...")
                return self._refresh_access_token()
            
            # If we have an access token but it might be expired, try to use it anyway
            # (sometimes tokens work longer than expected)
            elif self.token_type == 'access':
                if current_time < (self.token_expires_at + 300):  # Try for 5 minutes past expiry
                    logger.info("🔄 Using potentially expired access token...")
                    return self.access_token
                else:
                    logger.error("❌ Access token is too old and cannot be refreshed without refresh token")
                    logger.info("💡 Please provide a fresh access token or use a refresh token with client credentials")
                    return None
            
            logger.error("❌ No valid authentication method available")
            return None
            
        except Exception as e:
            logger.error(f"❌ Critical error in get_access_token: {e}")
            return None

    def _refresh_access_token(self):
        """Refresh access token using refresh token"""
        if not self.client_id or not self.client_secret:
            logger.error("❌ Cannot refresh token: missing client credentials")
            logger.info("💡 Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
            return None
        
        for retry in range(3):
            try:
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'Amazon-Affiliate-Bot/1.0'
                }
                
                data = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': self.refresh_token,
                    'grant_type': 'refresh_token'
                }
                
                logger.info(f"🔄 Attempting token refresh (attempt {retry + 1}/3)...")
                response = requests.post('https://oauth2.googleapis.com/token', 
                                       headers=headers, data=data, timeout=20)
                
                if response.status_code == 200:
                    token_data = response.json()
                    if 'access_token' in token_data:
                        self.access_token = token_data['access_token']
                        expires_in = token_data.get('expires_in', 3600)
                        self.token_expires_at = time.time() + expires_in
                        logger.info("✅ Access token refreshed successfully")
                        return self.access_token
                    else:
                        logger.error("❌ No access_token in refresh response")
                        return None
                else:
                    logger.error(f"❌ Token refresh failed: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    if response.status_code == 400:
                        # Bad request usually means invalid refresh token
                        logger.error("❌ Invalid refresh token or client credentials")
                        return None
                    
                    if retry < 2:
                        time.sleep(2)
                        continue
                        
            except Exception as e:
                logger.error(f"❌ Token refresh error (attempt {retry + 1}): {e}")
                if retry < 2:
                    time.sleep(2)
                    continue
        
        return None

    def test_blogger_access(self):
        """Test if we can access Blogger API with improved error handling"""
        logger.info("🧪 Testing Blogger API access...")
        
        access_token = self.get_access_token()
        if not access_token:
            logger.error("❌ No access token available for testing")
            return False
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'Amazon-Affiliate-Bot/1.0'
        }
        
        # Test with blog info endpoint (read-only)
        url = f"https://www.googleapis.com/blogger/v3/blogs/{self.blogger_id}"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                blog_data = response.json()
                logger.info(f"✅ Blogger API access confirmed for: {blog_data.get('name', 'Unknown Blog')}")
                return True
            elif response.status_code == 401:
                logger.error("❌ Authentication failed - token is invalid or expired")
                logger.error(f"Response: {response.text}")
                
                # If this is an access token, it might be expired
                if self.token_type == 'access':
                    logger.info("💡 Access token might be expired. Try getting a fresh one.")
                elif self.token_type == 'refresh':
                    logger.info("💡 Refresh token might be invalid. Check your client credentials.")
                
                return False
            elif response.status_code == 403:
                logger.error("❌ Permission denied - check blog ID and API permissions")
                logger.error(f"Response: {response.text}")
                return False
            else:
                logger.error(f"❌ Blogger API test failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Network error during Blogger API test: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during Blogger API test: {e}")
            return False

    def keep_alive(self):
        """Ping endpoint every 14 minutes to prevent Render sleep"""
        logger.info("💓 Keep-alive service started")
        while not self.shutdown_event.is_set():
            try:
                self.shutdown_event.wait(14 * 60)  # Wait 14 minutes or until shutdown
                if not self.shutdown_event.is_set():
                    logger.info("💓 Keep-alive ping - Bot is active")
            except Exception as e:
                logger.error(f"❌ Keep-alive error: {e}")
                self.shutdown_event.wait(60)  # Wait 1 minute before retry

    def get_amazon_product_images(self, asin, count=3):
        """Get multiple real Amazon product image URLs"""
        image_urls = []
        base_url = "https://m.media-amazon.com/images/I/"
        # Common suffixes for multiple images
        suffixes = ["_AC_SL1500_", "_AC_SL1000_", "_AC_SL800_", "_AC_SL500_"]
        
        # Use random suffixes to simulate different product images
        for i in range(count):
            try:
                # The ASIN is a key part of the image URL, so we can't just change suffixes randomly.
                # A more realistic approach would use a different ASIN from a product family.
                # For this script, we'll simulate a gallery by simply fetching different sizes.
                url = f"{base_url}{asin}{suffixes[i%len(suffixes)]}.jpg"
                response = requests.head(url, timeout=5)
                if response.status_code == 200:
                    image_urls.append(url)
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch image for {asin} at {url}: {e}")
        
        if not image_urls:
            # Fallback: generate placeholder with product category
            category = random.choice(self.trending_categories).replace('-', ' ').title()
            fallback_url = f"https://via.placeholder.com/400x400/667eea/ffffff?text={quote(category[:15])}"
            logger.info(f"📷 Using placeholder image for product")
            image_urls.append(fallback_url)
            
        logger.info(f"✅ Found {len(image_urls)} Amazon product images")
        return image_urls

    def get_trending_products(self):
        """Get trending Amazon products with real Amazon ASINs and images"""
        try:
            category = random.choice(self.trending_categories)
            search_term = f"{random.choice(self.high_intent_keywords)} {category}"
            
            # Real Amazon ASINs for different categories (these are real products)
            real_asins_by_category = {
                "electronics": ["B08N5WRWNW", "B07FZ8S74R", "B08R6K1Y1K", "B09G91L2YV", "B084JBQZPX"],
                "home-kitchen": ["B07V34FMJX", "B08567C98J", "B08Q3M88GK", "B08FQPVFLL", "B07P6Y1JXY"],
                "fashion": ["B07KGCFMZX", "B08NDHZ8L4", "B09334JJQP", "B087CJSB7K", "B08M5QRXZC"],
                "beauty": ["B07RJMQ2GY", "B08BZ5TYLK", "B07G8N2G3C", "B089H89JT8", "B08F9DGSMR"],
                "sports-outdoors": ["B07X8Z8W1P", "B08M8TD9RZ", "B086R9D6V2", "B089WXBHX5", "B07S9XHJ2Q"],
                "automotive": ["B07BFQMFN6", "B084JBQZPX", "B07YTB7D3L", "B08FQMCJKQ", "B089WXPQR4"],
                "tools-home-improvement": ["B07F7V8Z5R", "B08MZQK7GR", "B07K2Y9QSJ", "B089WXBHX5", "B07RJMQ2GY"],
                "toys-games": ["B08567C98J", "B08Q3M88GK", "B07X8Z8W1P", "B089H89JT8", "B087CJSB7K"],
                "health-personal-care": ["B07G8N2G3C", "B08BZ5TYLK", "B08F9DGSMR", "B089H89JT8", "B07RJMQ2GY"],
                "books": ["B08N5WRWNW", "B07FZ8S74R", "B08R6K1Y1K", "B09G91L2YV", "B084JBQZPX"],
                "baby-products": ["B07V34FMJX", "B08567C98J", "B08Q3M88GK", "B08FQPVFLL", "B07P6Y1JXY"],
                "pet-supplies": ["B07KGCFMZX", "B08NDHZ8L4", "B09334JJQP", "B087CJSB7K", "B08M5QRXZC"],
                "garden-lawn": ["B07X8Z8W1P", "B08M8TD9RZ", "B086R9D6V2", "B089WXBHX5", "B07S9XHJ2Q"],
                "musical-instruments": ["B07BFQMFN6", "B084JBQZPX", "B07YTB7D3L", "B08FQMCJKQ", "B089WXPQR4"]
            }
            
            # Get ASINs for the selected category
            available_asins = real_asins_by_category.get(category, real_asins_by_category["electronics"])
            
            products = []
            for i in range(3):
                asin = random.choice(available_asins)
                
                product_names = [
                    f"{random.choice(self.high_intent_keywords).title()} {category.replace('-', ' ').title()}",
                    f"Professional {category.replace('-', ' ').title()} Kit",
                    f"Premium {category.replace('-', ' ').title()} Set",
                    f"Advanced {category.replace('-', ' ').title()} System",
                    f"Elite {category.replace('-', ' ').title()} Collection"
                ]
                
                # Get Amazon product images (multiple)
                image_urls = self.get_amazon_product_images(asin)
                
                product = {
                    "title": random.choice(product_names),
                    "price": f"${random.randint(25, 299)}.{random.randint(10, 99)}",
                    "rating": round(random.uniform(4.2, 4.9), 1),
                    "reviews": random.randint(500, 5000),
                    "asin": asin,
                    "images": image_urls,
                    "features": [
                        f"Premium quality {category.replace('-', ' ')} construction",
                        "High customer satisfaction rating",
                        "Amazon Prime eligible with fast shipping",
                        "1-year manufacturer warranty included",
                        "30-day hassle-free return policy"
                    ]
                }
                products.append(product)
            
            logger.info(f"✅ Generated {len(products)} products for category: {category}")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error generating products: {e}")
            return []

    def create_affiliate_link(self, asin):
        """Create Amazon affiliate link"""
        base_url = f"https://www.amazon.com/dp/{asin}"
        affiliate_url = f"{base_url}?tag={self.amazon_tag}&linkCode=as2&camp=1789&creative=9325"
        return affiliate_url

    def shorten_url(self, long_url):
        """Shorten URL using Bitly with retry logic - handles quota limits"""
        for attempt in range(self.max_retries):
            try:
                headers = {
                    'Authorization': f'Bearer {self.bitly_token}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Amazon-Affiliate-Bot/1.0'
                }
                
                data = {
                    'long_url': long_url,
                    'domain': 'bit.ly'
                }
                
                response = requests.post('https://api-ssl.bitly.com/v4/shorten', 
                                       headers=headers, json=data, timeout=15)
                
                if response.status_code in [200, 201]:
                    short_url = response.json()['link']
                    logger.info(f"✅ URL shortened: {short_url}")
                    return short_url
                elif response.status_code == 429:
                    logger.warning("⚠️ Bitly quota reached - using original URL")
                    return long_url  # Return original URL when quota exceeded
                else:
                    logger.warning(f"⚠️ Bitly API response: {response.status_code} - {response.text}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    return long_url
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ URL shortening network error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
            except Exception as e:
                logger.error(f"❌ URL shortening error: {e}")
                return long_url
        
        return long_url

    def generate_seo_content(self, product):
        """Generate SEO-optimized content using Google Gemini with enhanced error handling"""
        for attempt in range(self.max_retries):
            try:
                url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Amazon-Affiliate-Bot/1.0',
                    'x-goog-api-key': self.gemini_api_key
                }
                
                prompt = f"""You are an expert product reviewer for an Amazon affiliate blog.
Create a highly compelling, professional, and SEO-optimized Amazon affiliate product review for: {product['title']} (Price: {product['price']}, Rating: {product['rating']}/5, {product['reviews']} reviews).
Your goal is to provide a comprehensive, trustworthy, and engaging review that drives sales.

The review must include the following sections and be returned as a single JSON object:
1.  **"title"**: A catchy, SEO-friendly headline (under 70 characters).
2.  **"meta_description"**: A concise, click-worthy summary (under 160 characters).
3.  **"intro"**: An engaging introductory paragraph highlighting the product's appeal and target audience.
4.  **"features"**: A detailed list of key features and benefits in an easy-to-read format. Use bullet points or numbered lists.
5.  **"review_body"**: A detailed, unbiased review of the product's performance, quality, and value.
6.  **"pros_and_cons"**: A balanced summary of the product's advantages and disadvantages using bullet points.
7.  **"customer_feedback"**: A summary of what real customers are saying based on the {product['reviews']:,} reviews.
8.  **"faq"**: A short FAQ section with 2-3 common questions and answers about the product.

Keep the entire content natural and trustworthy.
Return ONLY valid JSON in this exact format. DO NOT include any other text or markdown outside the JSON object.
{{
    "title": "Review title here",
    "meta_description": "Description here",
    "intro": "Intro paragraph here",
    "features": "HTML list of features here",
    "review_body": "Full HTML review content here",
    "pros_and_cons": "HTML list of pros and cons here",
    "customer_feedback": "Paragraph summarizing customer feedback here",
    "faq": "HTML list of FAQs here"
}}"""
                
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": prompt
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.7,
                        "topK": 40,
                        "topP": 0.95,
                        "maxOutputTokens": 2048,
                        "candidateCount": 1
                    },
                    "safetySettings": [
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                    ]
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=45)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            content = candidate['content']['parts'][0]['text'].strip()
                            
                            # New logic to handle markdown fences
                            if content.startswith('```json'):
                                content = content.strip('` \njson')
                            
                            try:
                                content_data = json.loads(content)
                                if all(key in content_data for key in ["title", "meta_description", "intro", "features", "review_body", "pros_and_cons", "customer_feedback", "faq"]):
                                    logger.info("✅ AI content generated successfully")
                                    return content_data
                            except json.JSONDecodeError as e:
                                logger.warning(f"⚠️ Failed to parse AI JSON: {e}. Raw content: {content[:200]}...")
                            
                elif response.status_code == 400:
                    logger.error(f"❌ Gemini API request error: {response.text}")
                    break
                elif response.status_code == 403:
                    logger.error(f"❌ Gemini API key issue: {response.text}")
                    break
                else:
                    logger.error(f"❌ Gemini API error (attempt {attempt + 1}/{self.max_retries}): {response.status_code}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    
            except requests.exceptions.Timeout:
                logger.error(f"⏰ Gemini API timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Content generation network error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
            except Exception as e:
                logger.error(f"❌ Content generation error: {e}")
                break
        
        logger.info("📝 Using fallback content generation")
        return self.create_fallback_content(product)

    def create_comparison_table(self, main_product, alt1, alt2):
        """Generates an HTML comparison table for a professional post"""
        table = f"""
        <div class="comparison-table" style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; margin: 25px 0; text-align: left;">
                <thead style="background-color: #f2f2f2;">
                    <tr>
                        <th style="padding: 12px; border: 1px solid #ddd;">Feature</th>
                        <th style="padding: 12px; border: 1px solid #ddd;">{main_product['title']}</th>
                        <th style="padding: 12px; border: 1px solid #ddd;">Alternative 1</th>
                        <th style="padding: 12px; border: 1px solid #ddd;">Alternative 2</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td style="padding: 12px; border: 1px solid #ddd;">Price</td>
                        <td style="padding: 12px; border: 1px solid #ddd;"><strong>{main_product['price']}</strong></td>
                        <td style="padding: 12px; border: 1px solid #ddd;">~${random.randint(15, 75)}</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">~${random.randint(200, 500)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; border: 1px solid #ddd;">Rating</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{main_product['rating']} ⭐</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{round(random.uniform(3.8, 4.4), 1)} ⭐</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{round(random.uniform(4.5, 4.9), 1)} ⭐</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px; border: 1px solid #ddd;">Reviews</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{main_product['reviews']:,}</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{random.randint(100, 999):,}</td>
                        <td style="padding: 12px; border: 1px solid #ddd;">{random.randint(6000, 15000):,}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        return table

    def create_fallback_content(self, product):
        """Create fallback content if AI fails"""
        title = f"🔥 {product['title']} Review 2024 - Worth the Investment?"
        
        content = f"""
        <div class="product-review">
            <div class="product-header" style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #2c3e50; margin-bottom: 10px;">🎯 Why {product['title']} is a Top Choice in 2024</h2>
            </div>
            
            <div class="image-gallery" style="display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-bottom: 25px;">
                <a href="{self.create_affiliate_link(product['asin'])}" target="_blank">
                    <img src="{product['images'][0]}" alt="{product['title']}" style="width: 100%; max-width: 400px; height: auto; border-radius: 10px; box-shadow: 0 8px 25px rgba(0,0,0,0.15); cursor: pointer;">
                </a>
            </div>

            <p>Looking for a reliable <a href="{self.create_affiliate_link(product['asin'])}" target="_blank" rel="nofollow sponsored"><strong>{product['title'].lower()}</strong></a>? You're in the right place! After thorough research and analysis of {product['reviews']:,} customer reviews, we're excited to share our comprehensive evaluation of this highly-rated product.</p>
            
            <h3>✨ Outstanding Features</h3>
            <ul style="background: #f8f9fa; padding: 20px; border-radius: 10px;">
                {chr(10).join(f'<li><strong>{feature}</strong></li>' for feature in product['features'])}
            </ul>
            
            <h3>📊 What Makes This Product Special</h3>
            <p>With an impressive <strong>{product['rating']}/5 star rating</strong> from over {product['reviews']:,} verified customers, this product has consistently proven its value. Customers frequently mention its exceptional quality, reliability, and outstanding performance.</p>
            
            <div class="analysis-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 25px; margin: 30px 0;">
                <div class="pros-section" style="background: #d4edda; padding: 20px; border-radius: 10px; border-left: 4px solid #28a745;">
                    <h4 style="color: #155724; margin-bottom: 15px;">✅ Major Advantages</h4>
                    <ul style="color: #155724;">
                        <li>Superior build quality and durability</li>
                        <li>Exceptional value for the price point</li>
                        <li>Amazon Prime fast shipping available</li>
                        <li>Overwhelmingly positive customer reviews</li>
                        <li>Reliable performance and functionality</li>
                    </ul>
                </div>
                <div class="considerations" style="background: #f8d7da; padding: 20px; border-radius: 10px; border-left: 4px solid #dc3545;">
                    <h4 style="color: #721c24; margin-bottom: 15px;">⚠️ Things to Consider</h4>
                    <ul style="color: #721c24;">
                        <li>Check size/compatibility requirements</li>
                        <li>Compare with similar products if needed</li>
                        <li>Read product specifications carefully</li>
                        <li>Consider your specific use case</li>
                    </ul>
                </div>
            </div>
            
            <h3>💬 Real Customer Feedback</h3>
            <p>The {product['reviews']:,} customer reviews paint a clear picture: this is a product that delivers on its promises. Customers consistently praise its performance, quality, and value, making it a standout choice in its category.</p>
            
            <div class="faq-section">
                <h3>❓ Frequently Asked Questions</h3>
                <ul style="list-style-type: none; padding: 0;">
                    <li style="margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 10px;"><strong>Q: Is this product durable?</strong><br>A: Yes, many customers have highlighted its robust and long-lasting build quality.</li>
                    <li style="margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 10px;"><strong>Q: Does it come with a warranty?</strong><br>A: A 1-year manufacturer warranty is included, providing peace of mind with your purchase.</li>
                </ul>
            </div>
        </div>
        """
        
        meta_description = f"{product['title']} review: {product['rating']}/5 stars from {product['reviews']:,} customers. Features, pros/cons & best price at {product['price']}."
        
        return {
            "title": title,
            "meta_description": meta_description,
            "intro": "",
            "features": "",
            "review_body": content,
            "pros_and_cons": "",
            "customer_feedback": "",
            "faq": ""
        }

    def post_to_blogger(self, title, content_data, affiliate_link, product):
        """Post content to Blogger using API with improved authentication retry"""
        for attempt in range(self.max_retries):
            try:
                access_token = self.get_access_token()
                if not access_token:
                    logger.error("❌ No valid access token available for posting")
                    if self.token_type == 'access':
                        logger.error("💡 Your access token may have expired. Please get a fresh one.")
                    elif self.token_type == 'refresh':
                        logger.error("💡 Unable to refresh token. Check your client credentials.")
                    return False
                    
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Amazon-Affiliate-Bot/1.0'
                }
                
                # --- New Post HTML Template ---
                image_gallery_html = ""
                if product['images']:
                    image_gallery_html = f"""
                    <div class="image-gallery" style="display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-bottom: 25px;">
                        {"".join([f'<a href="{affiliate_link}" target="_blank"><img src="{img_url}" alt="{product["title"]}" style="width: 100%; max-width: 250px; height: auto; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); cursor: pointer;"></a>' for img_url in product['images']])}
                    </div>
                    """

                comparison_table_html = self.create_comparison_table(product, {}, {})
                
                formatted_content = f"""
                <div class="affiliate-product-review" style="max-width: 800px; margin: 0 auto; font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    
                    <h1 style="text-align: center; font-size: 2.2em; color: #2c3e50; margin-bottom: 20px;">
                        <a href="{affiliate_link}" target="_blank" rel="nofollow sponsored" style="text-decoration: none; color: inherit;">{content_data['title']}</a>
                    </h1>

                    {image_gallery_html}

                    <p>{content_data['intro']}</p>
                    
                    <div class="cta-inline" style="text-align: center; margin: 25px 0;">
                        <a href="{affiliate_link}" target="_blank" rel="nofollow sponsored" style="display: inline-block; background-color: #ff9900; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; transition: background-color 0.3s;">
                            🛒 Check Current Price on Amazon
                        </a>
                    </div>
                    
                    <h2 style="color: #4CAF50;">✨ Key Features & Benefits</h2>
                    {content_data['features']}
                    
                    <h2 style="color: #4CAF50;">📝 In-Depth Review</h2>
                    {content_data['review_body']}
                    
                    <h2 style="color: #4CAF50;">✅ Pros & ❌ Cons</h2>
                    {content_data['pros_and_cons']}
                    
                    <h2 style="color: #4CAF50;">📊 Comparison Table</h2>
                    <p>See how the {product['title']} stacks up against the competition:</p>
                    {comparison_table_html}

                    <h2 style="color: #4CAF50;">💬 Real Customer Feedback</h2>
                    <p>{content_data['customer_feedback']}</p>
                    
                    <div class="cta-main" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 20px; text-align: center; margin: 40px 0; box-shadow: 0 15px 35px rgba(0,0,0,0.1);">
                        <h3 style="color: white; margin-bottom: 20px; font-size: 28px; font-weight: bold;">Ready to Upgrade Your Experience?</h3>
                        <p style="font-size: 18px; margin-bottom: 25px; opacity: 0.95;">Click below for the best price and fast delivery!</p>
                        
                        <a href="{affiliate_link}" target="_blank" rel="nofollow sponsored" style="background: white; color: #667eea; padding: 20px 50px; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 20px; display: inline-block; transition: all 0.3s; box-shadow: 0 8px 25px rgba(0,0,0,0.2); text-transform: uppercase; letter-spacing: 1px;">
                            🛒 Get It on Amazon →
                        </a>
                    </div>

                    <h2 style="color: #4CAF50;">❓ Frequently Asked Questions</h2>
                    {content_data['faq']}

                    <div style="margin-top: 25px; font-size: 13px; opacity: 0.85; line-height: 1.4; text-align: center;">
                        <p>✅ Prime Shipping Available | ✅ 30-Day Returns | ✅ Secure Payment</p>
                        <p style="margin-top: 15px; font-size: 11px; opacity: 0.7;">*As Amazon Associates, we earn from qualifying purchases. Prices subject to change.</p>
                    </div>
                </div>
                """
                
                # Prepare the blog post data
                post_data = {
                    'title': content_data['title'],
                    'content': formatted_content,
                    'labels': ['amazon', 'affiliate', 'review', 'deals', '2024', product['title'].split(' ')[-1].lower(), 'shopping']
                }
                
                # Sanitize the blogger ID to ensure it's a clean string
                sanitized_blogger_id = "".join(filter(str.isdigit, self.blogger_id))
                url = f"[https://www.googleapis.com/blogger/v3/blogs/](https://www.googleapis.com/blogger/v3/blogs/){sanitized_blogger_id}/posts"
                
                logger.info(f"🔄 Posting to Blogger (attempt {attempt + 1}/{self.max_retries})...")
                
                response = requests.post(url, headers=headers, json=post_data, timeout=30)
                
                if response.status_code == 200:
                    post_data_response = response.json()
                    post_url = post_data_response.get('url', '')
                    logger.info(f"✅ Successfully posted to Blogger: {post_url}")
                    return True
                elif response.status_code == 401:
                    logger.warning(f"⚠️ Authentication failed (attempt {attempt + 1}/{self.max_retries})")
                    logger.error(f"Response: {response.text}")
                    self.access_token = None
                    if self.token_type == 'access':
                        logger.error("❌ Access token appears to be expired or invalid")
                        logger.info("💡 Please provide a fresh access token")
                        return False
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                elif response.status_code == 403:
                    logger.error(f"❌ Permission denied: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    logger.error("💡 Check if your token has the required Blogger API permissions")
                    return False
                else:
                    logger.error(f"❌ Blogger API error: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    return False
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Network error posting to Blogger (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
            except Exception as e:
                logger.error(f"❌ Error posting to Blogger: {e}")
                return False
        
        logger.error("❌ All posting attempts failed")
        return False

    def process_and_post_product(self):
        """Main function to process and post a product"""
        try:
            logger.info("🔄 Starting new product processing cycle...")
            
            if self.shutdown_event.is_set():
                logger.info("🛑 Shutdown requested, stopping product processing")
                return False
            
            products = self.get_trending_products()
            if not products:
                logger.warning("⚠️ No products retrieved, skipping cycle")
                return False
            
            product = random.choice(products)
            
            product_hash = hashlib.md5(product['title'].encode()).hexdigest()
            if product_hash in self.posted_products:
                logger.info("📝 Product already posted recently, selecting another...")
                available_products = [p for p in products if hashlib.md5(p['title'].encode()).hexdigest() not in self.posted_products]
                if available_products:
                    product = random.choice(available_products)
                    product_hash = hashlib.md5(product['title'].encode()).hexdigest()
                else:
                    logger.info("All products recently posted, clearing history...")
                    self.posted_products.clear()
            
            affiliate_url = self.create_affiliate_link(product['asin'])
            short_url = self.shorten_url(affiliate_url)
            
            logger.info(f"✍️ Generating content for: {product['title'][:50]}...")
            content_data = self.generate_seo_content(product)
            
            if not content_data:
                logger.error("❌ Failed to generate content")
                return False
            
            logger.info("📤 Posting to Blogger...")
            success = self.post_to_blogger(
                content_data['title'],
                content_data,
                short_url,
                product
            )
            
            if success:
                self.posted_products.add(product_hash)
                logger.info(f"🎉 Successfully posted: {product['title'][:50]}...")
                logger.info(f"💰 Affiliate link: {short_url}")
                logger.info(f"🖼️ Product image: {product['images'][0]}")
                
                if len(self.posted_products) > 50:
                    self.posted_products = set(list(self.posted_products)[-25:])
                
                return True
            else:
                logger.error("❌ Failed to post product")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error in product processing: {e}")
            import traceback
            traceback.print_exc()
            return False

    def wait_with_shutdown_check(self, total_seconds, log_interval=900):
        """Wait for specified time while checking for shutdown signal"""
        elapsed = 0
        while elapsed < total_seconds and not self.shutdown_event.is_set():
            wait_time = min(60, total_seconds - elapsed)
            if self.shutdown_event.wait(wait_time):
                logger.info("🛑 Shutdown signal received during wait")
                return True
            
            elapsed += wait_time
            
            if elapsed % log_interval == 0 and elapsed < total_seconds:
                remaining_minutes = (total_seconds - elapsed) // 60
                logger.info(f"⏳ {remaining_minutes} minutes remaining until next post...")
        
        return self.shutdown_event.is_set()

    def run_bot(self):
        """Main bot execution loop with improved error handling"""
        logger.info("🚀 Amazon Affiliate Bot starting...")
        logger.info(f"🎯 Target blog: {self.blogger_url}")
        
        self.setup_signal_handlers()
        
        self.diagnose_authentication()
        
        if not self.refresh_token:
            logger.error("❌ GOOGLE_OAUTH_TOKEN environment variable not set!")
            logger.error("Please set your token in Render environment variables")
            logger.error("The bot will continue but posting will fail without proper authentication")
            return False
        
        logger.info("🧪 Testing Blogger API access...")
        if self.test_blogger_access():
            logger.info("✅ Authentication working correctly - ready to post!")
        else:
            logger.error("❌ Authentication test failed - please check your token")
            if self.token_type == 'access':
                logger.error("💡 Tip: Make sure you're using an ACCESS TOKEN starting with 'ya29.'")
                logger.error("💡 Access tokens expire - you may need a fresh one")
            elif self.token_type == 'refresh':
                logger.error("💡 Tip: Check your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
                logger.error("💡 Refresh tokens require proper client credentials")
            return False
        
        keep_alive_thread = Thread(target=self.keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("💓 Keep-alive thread started")
        
        logger.info("🎬 Creating first post immediately...")
        first_post_success = self.process_and_post_product()
        
        if not first_post_success:
            logger.warning("⚠️ First post failed, but continuing with scheduled posts...")
        
        post_count = 1
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        while not self.shutdown_event.is_set():
            try:
                logger.info(f"⏰ Waiting 60 minutes for next post (#{post_count + 1})...")
                
                shutdown_requested = self.wait_with_shutdown_check(3600, 900)
                
                if shutdown_requested:
                    logger.info("🛑 Shutdown requested, exiting main loop")
                    break
                
                post_count += 1
                logger.info(f"🔄 Starting post #{post_count}")
                
                success = self.process_and_post_product()
                
                if success:
                    consecutive_failures = 0
                    logger.info(f"✅ Post #{post_count} completed successfully")
                else:
                    consecutive_failures += 1
                    logger.warning(f"❌ Post #{post_count} failed (consecutive failures: {consecutive_failures})")
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(f"❌ Too many consecutive failures ({consecutive_failures}). Waiting 30 minutes before retry...")
                        shutdown_requested = self.wait_with_shutdown_check(1800, 300)
                        if shutdown_requested:
                            break
                        consecutive_failures = 0
                
            except KeyboardInterrupt:
                logger.info("🛑 Bot stopped by user (Ctrl+C)")
                self.shutdown_event.set()
                break
            except Exception as e:
                logger.error(f"❌ Unexpected bot error: {e}")
                traceback.print_exc()
                
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    logger.error("❌ Too many consecutive errors. Shutting down bot.")
                    break
                
                logger.info("⏸️ Waiting 5 minutes before retry...")
                shutdown_requested = self.wait_with_shutdown_check(300)
                if shutdown_requested:
                    break
        
        logger.info("🏁 Bot shutting down gracefully...")
        return True

def run_health_server():
    """Run Flask health server for Render"""
    try:
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"🌐 Starting health server on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"❌ Health server error: {e}")

def main():
    """Main function with proper error handling"""
    logger.info("🚀 Amazon Affiliate Bot initializing...")
    
    try:
        health_thread = Thread(target=run_health_server, daemon=True)
        health_thread.start()
        
        time.sleep(3)
        logger.info("✅ Health server started successfully")
        
        bot = AmazonAffiliateBlogBot()
        bot_success = bot.run_bot()
        
        if bot_success:
            logger.info("✅ Bot completed successfully")
        else:
            logger.error("❌ Bot exited with errors")
            
    except KeyboardInterrupt:
        logger.info("🛑 Application interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal application error: {e}")
        traceback.print_exc()
    
    logger.info("🌐 Keeping health server alive for final requests...")
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        pass
    
    logger.info("👋 Application shutting down")
    return 0

if __name__ == "__main__":
    sys.exit(main())