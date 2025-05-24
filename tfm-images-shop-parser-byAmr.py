import os
import asyncio
import aiohttp
import aiofiles
import json
from urllib.parse import urlparse, unquote

# --- Settings ---
BASE_DOWNLOAD_FOLDER = "TFM_DOWNLOADED_ASSETS"  # Main folder to save everything
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36" # Standard User-Agent

async def download_item(session: aiohttp.ClientSession, url: str, base_folder: str):
    """
    Downloads a single item (file) from a URL and saves it locally,
    creating necessary directories.
    """
    local_filepath = "N/A" # Initialize for error reporting
    try:
        print(f"[INFO] Processing URL: {url}")
        async with session.get(url) as resp:
            if resp.status == 200:
                content_to_write = await resp.read()

                # --- Improved Path Handling ---
                parsed_url = urlparse(url)
                # Remove any query parameters from the path to get the correct filename/folder structure
                path_without_query = unquote(parsed_url.path.split('?')[0])

                # Remove leading slash if present to ensure os.path.join works correctly
                if path_without_query.startswith('/'):
                    path_without_query = path_without_query[1:]

                # Construct the full local filepath
                # Example: base_folder = "TFM_DOWNLOADED_ASSETS"
                # path_without_query = "images/maps/map1.png"
                # local_filepath = "TFM_DOWNLOADED_ASSETS/images/maps/map1.png"
                local_filepath = os.path.join(base_folder, path_without_query)

                # Create parent directories for the file if they don't exist
                local_dir = os.path.dirname(local_filepath)
                if not os.path.exists(local_dir):
                    print(f"[+] Creating directory: {local_dir}")
                    os.makedirs(local_dir, exist_ok=True)
                # --- End of Improved Path Handling ---

                # Check if file exists and content matches (can be simplified if not needed)
                if os.path.exists(local_filepath):
                    try:
                        async with aiofiles.open(local_filepath, mode='rb') as f_existing:
                            existing_content = await f_existing.read()
                        if existing_content == content_to_write:
                            print(f"[SKIP] File '{local_filepath}' already exists and content matches, skipping.")
                            return
                        else:
                            print(f"[WARN] File '{local_filepath}' exists but content differs. Overwriting.")
                    except Exception as e_read:
                        print(f"[WARN] Could not read existing file '{local_filepath}' for comparison: {e_read}. Overwriting.")

                async with aiofiles.open(local_filepath, mode='wb') as f:
                    await f.write(content_to_write)
                print(f"[SAVE] Saved '{os.path.basename(local_filepath)}' to '{local_dir}/'")

            elif resp.status == 404:
                print(f"[ERROR] File not found (404): {url}")
            else:
                print(f"[ERROR] Failed to download {url}. Status: {resp.status}")

    except aiohttp.ClientError as e:
        print(f"[NETWORK_ERROR] Could not connect or download {url}: {e}")
    except OSError as e:
        print(f"[OS_ERROR] Filesystem error for {url} (path: {local_filepath}): {e}")
    except Exception as e:
        print(f"[UNEXPECTED_ERROR] Downloading {url}: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for unexpected errors


async def start_downloads():
    print('[+] Transformice Asset Downloader')
    print('[+] Using combined list and direct downloads.')
    print(f'[+] Files will be saved to: {os.path.abspath(BASE_DOWNLOAD_FOLDER)}')
    print()

    # Create the base download directory if it doesn't exist
    if not os.path.exists(BASE_DOWNLOAD_FOLDER):
        os.makedirs(BASE_DOWNLOAD_FOLDER)
        print(f"[INFO] Created base download directory: {BASE_DOWNLOAD_FOLDER}")

    tasks = []
    # Add a User-Agent to the session
    async with aiohttp.ClientSession(headers={'User-Agent': USER_AGENT}) as session:
        # 1. Download from derpolino list (as in the original code)
        print("\n--- Fetching file list from derpolino.alwaysdata.net ---")
        derpolino_urls_to_download = []
        # These paths should be what getFiles.php expects for the 'n' parameter
        paths_for_derpolino = ['images', 'ar', 'godspaw', 'share', 'woot', 'wp-admin', 'wp-content', 'wp-includes']
        for html_path_segment in paths_for_derpolino:
            # Ensure the path segment is URL-encoded for the 'n' parameter
            php_url = f"http://derpolino.alwaysdata.net/imagetfm/getFiles.php?n={html_path_segment}%2F&mode=tfm"
            print(f"[INFO] Fetching from {php_url}")
            try:
                async with session.get(php_url) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        try:
                            # Assuming json.loads(...).values() gives a list of *path segments*
                            # that need "https://www.transformice.com/" prepended.
                            # Or it might give full URLs. We'll try to handle both.
                            data = json.loads(content.decode(errors='ignore'))
                            if isinstance(data, dict):
                                partial_urls = data.values()
                            elif isinstance(data, list): # If it's already a list of URLs/paths
                                partial_urls = data
                            else:
                                print(f"[ERROR] Unexpected JSON structure from {php_url}. Expected dict or list, got {type(data)}")
                                partial_urls = []

                            for p_url in partial_urls:
                                if not isinstance(p_url, str): # Skip if not a string URL/path
                                    print(f"[WARN] Non-string item in derpolino list: {p_url}. Skipping.")
                                    continue
                                if not p_url.startswith(('http://', 'https://')):
                                    full_url = f'https://www.transformice.com/{p_url.lstrip("/")}'
                                else:
                                    full_url = p_url  # If derpolino already provides a full URL
                                derpolino_urls_to_download.append(full_url)
                        except json.JSONDecodeError:
                            print(f"[ERROR] Could not decode JSON from {php_url}. Content (first 200 chars): {content[:200]}")
                        except Exception as e:
                            print(f"[ERROR] Error processing response from {php_url}: {e}")
                    else:
                        print(f"[ERROR] Failed to fetch from {php_url}. Status: {resp.status}")
            except Exception as e:
                print(f"[ERROR] Could not connect to or process {php_url}: {e}")

        for url in derpolino_urls_to_download:
            tasks.append(download_item(session, url, BASE_DOWNLOAD_FOLDER))
        print(f"--- Added {len(derpolino_urls_to_download)} URLs from derpolino for download ---")

        # 2. Download specific SWF files from x_bibliotheques
        print("\n--- Downloading specific SWF files from x_bibliotheques ---")
        bibliotheques_base = 'http://transformice.com/images/x_bibliotheques/'
        for binary in ["x_fourrures", "x_fourrures2", "x_fourrures3", "x_fourrures4", "x_meli_costumes", "x_pictos_editeur"]:
            tasks.append(download_item(session, f'{bibliotheques_base}{binary}.swf', BASE_DOWNLOAD_FOLDER))

        # 3. Download language files
        print("\n--- Downloading language files (tfz) ---")
        langues_base = 'http://transformice.com/langues/'
        # Note: these are likely binary files, not SWFs. The original code implies this.
        for langue in ['en', 'fr', 'br', 'es', 'cn', 'tr', 'vk', 'pl', 'hu', 'nl', 'ro', 'id', 'de', 'e2', 'ar', 'ph', 'lt', 'jp', 'ch', 'fi', 'cz', 'sk', 'hr', 'bu', 'lv', 'he', 'it', 'et', 'az', 'pt']:
            tasks.append(download_item(session, f'{langues_base}tfz_{langue}', BASE_DOWNLOAD_FOLDER))

        # 4. Download music files
        print("\n--- Downloading music files ---")
        musiques_base = 'http://transformice.com/images/musiques/'
        for music_num in range(4):  # 0, 1, 2, 3
            tasks.append(download_item(session, f'{musiques_base}tfm_{music_num}.mp3', BASE_DOWNLOAD_FOLDER))

        # Execute all download tasks concurrently
        if tasks:
            print(f"\n[INFO] Starting download of {len(tasks)} items...")
            await asyncio.gather(*tasks)
        else:
            print("[INFO] No items found to download from the specified lists.")

    print('\n--- Download process finished ---')
    input("Press Enter to exit...") # Cross-platform way to pause

async def main():
    # For Python 3.7+ you can use asyncio.run() directly
    await start_downloads()

if __name__ == "__main__":
    # On Windows, you might need this policy if you encounter issues with asyncio
    # especially in certain environments or older Python 3 versions.
    # if os.name == 'nt':
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main()) # Modern way to run asyncio (Python 3.7+)