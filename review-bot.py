import asyncio
import random
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from playwright.async_api import async_playwright
from asyncio import Semaphore
from datetime import datetime
import threading

# ====================== LOGGING ======================
logging.basicConfig(
    filename=f"review_manager_{datetime.now().strftime('%Y%m%d_%H%M')}.log",
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

class GoogleReviewBot:
    def __init__(self, gui_callback=None, max_concurrent=3, spread_hours=12):
        self.accounts = []
        self.proxies = []
        self.review_texts = []
        self.max_concurrent = max_concurrent
        self.spread_hours = spread_hours
        self.success_count = 0
        self.gui_callback = gui_callback

    def log(self, msg):
        logging.info(msg)
        if self.gui_callback:
            self.gui_callback(msg)

    def load_accounts(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Accounts file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split(':', 2)
                    if len(parts) >= 2:
                        self.accounts.append(parts)

    def load_proxies(self, file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Proxies file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            self.proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    def generate_review_texts(self, count, city):
        bases = [
            f"I had an amazing experience at this {city} business. The staff was super friendly and professional.",
            f"Best place I've visited in {city} recently. Everything was top quality.",
            f"Highly recommend this spot in {city}! Clean, great atmosphere, and excellent service.",
            f"Very satisfied with my visit here in {city}. Will definitely be coming back.",
            f"Outstanding service and attention to detail. One of the best in the {city} area.",
            f"Really impressed by how professional the team was during my visit.",
            f"Great local business with good prices and even better customer service.",
            f"Perfect experience at this place in {city}. Keep up the great work!"
        ]
        self.review_texts = [random.choice(bases) + " " + random.choice(["Thanks again!", "Highly recommended!", ""]) for _ in range(count)]

    async def warm_account(self, page):
        try:
            await page.goto("https://www.google.com", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(4, 8))
            search_box = page.locator('textarea[aria-label="Search"]')
            if await search_box.count() > 0:
                await search_box.click()
            await page.keyboard.type(random.choice(["local news", "weather forecast", "best restaurants"]), delay=random.uniform(70, 160))
            await asyncio.sleep(random.uniform(4, 9))
            await page.goto("https://maps.google.com", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(6, 12))
        except:
            pass

    async def handle_login(self, page, account):
        email = account[0]
        try:
            await page.goto("https://accounts.google.com/signin", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(3, 5))

            await page.fill('input[type="email"]', email)
            await page.click('button')
            await asyncio.sleep(random.uniform(4, 6))

            await page.fill('input[type="password"]', account[1])
            await page.click('button')
            await asyncio.sleep(random.uniform(5, 8))

            if len(account) > 2 and account[2]:
                if await page.locator('text=recovery').count() > 0:
                    await page.fill('input', account[2])
                    await page.click('button')
                    await asyncio.sleep(5)
            return True
        except Exception as e:
            self.log(f"Login failed {email[:10]}...: {e}")
            return False

    async def post_single_review(self, account, proxy_str, business_url, review_text):
        email = account[0]
        for attempt in range(3):
            try:
                clean_proxy = proxy_str.replace("http://", "").replace("https://", "")
                if '@' in clean_proxy:
                    auth, host = clean_proxy.split('@', 1)
                    user, pwd = auth.split(':', 1)
                    proxy_config = {"server": f"http://{host}", "username": user, "password": pwd}
                else:
                    proxy_config = {"server": f"http://{clean_proxy}"}

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, proxy=proxy_config)
                    context = await browser.new_context(
                        viewport={"width": random.randint(1366, 1920), "height": random.randint(768, 1080)},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                        locale=random.choice(["en-US", "en-GB"]),
                        timezone_id=random.choice(["America/Los_Angeles", "America/New_York"])
                    )
                    page = await context.new_page()

                    await self.warm_account(page)

                    if not await self.handle_login(page, account):
                        await browser.close()
                        continue

                    await page.goto(business_url, wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(5, 10))

                    await page.locator('button:has-text("Write a review")').first.click(timeout=18000)
                    await asyncio.sleep(random.uniform(3.5, 7))

                    await page.locator('div[role="radio"][aria-label*="5 stars"]').first.click(timeout=15000)
                    await asyncio.sleep(random.uniform(3, 6))

                    await page.locator('textarea').fill(review_text)
                    await asyncio.sleep(random.uniform(3, 6))
                    
                    await page.locator('button:has-text("Post"), button:has-text("Publish")').click()
                    await asyncio.sleep(random.uniform(8, 13))

                    self.log(f"SUCCESS → {email[:10]}... | Review posted")
                    await browser.close()
                    return True

            except Exception as e:
                self.log(f"Attempt {attempt+1} failed {email[:10]}... | {str(e)[:100]}")
                await asyncio.sleep(10)
        
        return False

    async def run(self, state, city, num_businesses, accounts_file, proxies_file):
        if not state.strip() or not city.strip():
            self.log("ERROR: State and City cannot be empty!")
            return 0, 0

        self.load_accounts(accounts_file)
        self.load_proxies(proxies_file)
        self.generate_review_texts(num_businesses, city)

        businesses = await self.find_businesses(state, city, num_businesses)
        actual_count = min(num_businesses, len(businesses))

        if actual_count == 0:
            self.log("ERROR: No businesses found. Cannot proceed.")
            return 0, 0
        if actual_count < num_businesses:
            self.log(f"WARNING: Only {actual_count}/{num_businesses} businesses found.")

        if len(self.accounts) < actual_count or len(self.proxies) < actual_count:
            self.log("ERROR: Not enough accounts or unique proxies!")
            return 0, 0

        semaphore = Semaphore(self.max_concurrent)
        base_delay = (self.spread_hours * 3600) / max(actual_count, 1)

        self.log(f"Starting {actual_count} reviews ({self.max_concurrent} concurrent, spread ~{self.spread_hours}h)...")

        async def safe_post(i):
            # Stagger start time
            await asyncio.sleep(i * base_delay / self.max_concurrent * random.uniform(0.6, 1.2))
            
            async with semaphore:
                result = await self.post_single_review(
                    self.accounts[i], self.proxies[i], businesses[i], self.review_texts[i]
                )
                if result:
                    self.success_count += 1
                return result

        tasks = [safe_post(i) for i in range(actual_count)]
        await asyncio.gather(*tasks)

        self.log(f"COMPLETED → {self.success_count}/{actual_count} successful reviews")
        return self.success_count, actual_count

    async def find_businesses(self, state, city, count):
        self.log(f"Searching random businesses in {city}, {state}...")
        businesses = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...")
            page = await context.new_page()
            
            try:
                await page.goto(f"https://www.google.com/maps/search/{city}+{state}", wait_until="domcontentloaded")
                await asyncio.sleep(8)
                
                for _ in range(7):
                    await page.keyboard.press('End')
                    await asyncio.sleep(3.2)
                
                cards = await page.locator('a[href*="/maps/place/"]').all()
                seen = set()
                for card in cards:
                    href = await card.get_attribute('href')
                    if href:
                        clean = href.split('!')[0].split('?')[0]
                        if clean not in seen:
                            seen.add(clean)
                            businesses.append(clean)
                            if len(businesses) >= count:
                                break
            except Exception as e:
                self.log(f"Scraping error: {e}")
            finally:
                await browser.close()
        
        self.log(f"Found {len(businesses)} businesses")
        return businesses[:count]

# ====================== GUI ======================
class BotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Business Review Manager")
        self.root.geometry("760x670")

        ttk.Label(self.root, text="Business Review Manager", font=("Arial", 18, "bold")).pack(pady=15)

        frame = ttk.Frame(self.root)
        frame.pack(pady=10, padx=30, fill="x")

        ttk.Label(frame, text="State:").grid(row=0, column=0, sticky="w", pady=5)
        self.state_var = tk.StringVar(value="California")
        ttk.Entry(frame, textvariable=self.state_var, width=35).grid(row=0, column=1, padx=10)

        ttk.Label(frame, text="City:").grid(row=1, column=0, sticky="w", pady=5)
        self.city_var = tk.StringVar(value="Los Angeles")
        ttk.Entry(frame, textvariable=self.city_var, width=35).grid(row=1, column=1, padx=10)

        ttk.Label(frame, text="Number of Reviews:").grid(row=2, column=0, sticky="w", pady=5)
        self.count_var = tk.IntVar(value=20)
        ttk.Entry(frame, textvariable=self.count_var, width=35).grid(row=2, column=1, padx=10)

        ttk.Label(frame, text="Max Concurrent:").grid(row=3, column=0, sticky="w", pady=5)
        self.concurrent_var = tk.IntVar(value=3)
        ttk.Entry(frame, textvariable=self.concurrent_var, width=35).grid(row=3, column=1, padx=10)

        ttk.Label(frame, text="Spread Over Hours:").grid(row=4, column=0, sticky="w", pady=5)
        self.spread_var = tk.IntVar(value=12)
        ttk.Entry(frame, textvariable=self.spread_var, width=35).grid(row=4, column=1, padx=10)

        ttk.Label(frame, text="Accounts File:").grid(row=5, column=0, sticky="w", pady=5)
        self.acc_file = tk.StringVar(value="googleaccounts.txt")
        ttk.Entry(frame, textvariable=self.acc_file, width=35).grid(row=5, column=1, padx=10)

        ttk.Label(frame, text="Proxies File:").grid(row=6, column=0, sticky="w", pady=5)
        self.proxy_file = tk.StringVar(value="proxies.txt")
        ttk.Entry(frame, textvariable=self.proxy_file, width=35).grid(row=6, column=1, padx=10)

        self.start_btn = ttk.Button(self.root, text="START REVIEW PROCESS", command=self.start_bot)
        self.start_btn.pack(pady=25)

        self.status = tk.Text(self.root, height=20, width=90, font=("Consolas", 9))
        self.status.pack(pady=10, padx=30)

    def log(self, msg):
        def update():
            self.status.insert(tk.END, f"{msg}\n")
            self.status.see(tk.END)
        self.root.after(0, update)

    def start_bot(self):
        try:
            num = int(self.count_var.get())
            concurrent = int(self.concurrent_var.get())
            spread = int(self.spread_var.get())
            if num <= 0 or concurrent <= 0 or spread <= 0:
                messagebox.showerror("Error", "All numbers must be positive")
                return
        except (ValueError, tk.TclError):
            messagebox.showerror("Error", "Invalid input values")
            return

        self.start_btn.config(state="disabled")
        self.log("=== Bot Started ===")

        def run_in_thread():
            success = 0
            total = 0
            try:
                bot = GoogleReviewBot(
                    gui_callback=self.log, 
                    max_concurrent=concurrent,
                    spread_hours=spread
                )
                result = asyncio.run(bot.run(
                    state=self.state_var.get().strip(),
                    city=self.city_var.get().strip(),
                    num_businesses=num,
                    accounts_file=self.acc_file.get(),
                    proxies_file=self.proxy_file.get()
                ))
                if isinstance(result, tuple):
                    success, total = result
            except Exception as e:
                self.log(f"CRITICAL ERROR: {e}")
            finally:
                self.root.after(0, lambda: self.on_finish(success, total))

        threading.Thread(target=run_in_thread, daemon=True).start()

    def on_finish(self, success, total):
        self.start_btn.config(state="normal")
        self.log("=== Process Finished ===")
        messagebox.showinfo("Done", f"Review process completed!\n\n{success}/{total} reviews successful.\nCheck log file for full details.")

    def run(self):
        self.root.mainloop()

# ====================== LAUNCH ======================
if __name__ == "__main__":
    gui = BotGUI()
    gui.run()