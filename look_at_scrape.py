import pickle
from pathlib import Path
from pprint import pprint
from scrape import *

def load_scraper_state(file_path: str):
    with open(file_path, 'rb') as f:
        return pickle.load(f)

def display_equivalence_classes(equiv_classes):
    print(f"Total Equivalence Classes: {len(equiv_classes.urls)}")
    print("Equivalence Classes:")
    for i, url_state in enumerate(equiv_classes.urls.values(), start=1):
        print(f"\nEquivalence Class {i}:")
        print(f"  Page URLs: {url_state.aliases}")
        print(f"  Total Unique Actions: {len(url_state.unique_samples)}")
        print("  Unique Actions:")
        for j, sample in enumerate(url_state.unique_samples.values(), start=1):
            # if len(sample) > 1:
            #     print("*" * 80)
            #     print(len(sample))
            for action_info in sample:
                print(f"    Action {j}:")
                # print(f"      Action HTML: {action_info.action.html}")
                # print(f"      Action XPath: {action_info.action.xpath}")
                # print(f"      Before HTML: {action_info.before_html[:100]}...")
                # print(f"      After HTML: {action_info.after_html[:100]}...")
                print(f"      Before Screenshot: {action_info.before_screenshot}")
                print(f"      After Screenshot: {action_info.after_screenshot}")
                print(f"      Tree Line: {action_info.action.tree_line}")
                print()

        input("Press Enter to continue to the next equivalence class...")

def main():
    scraper_state_file = 'dominos/scraper_state.pkl'
    equiv_classes = load_scraper_state(scraper_state_file)
    display_equivalence_classes(equiv_classes)

if __name__ == '__main__':
    main()