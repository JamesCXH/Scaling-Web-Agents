import os
def modify_effect_txt(directory, search_replace_dict):
    for root, dirs, files in os.walk(directory):
        if 'effect.txt' in files:
            effect_file_path = os.path.join(root, 'effect.txt')

            with open(effect_file_path, 'r') as file:
                content = file.read()

            if content.strip() in search_replace_dict:
                with open(effect_file_path, 'w') as file:
                    file.write(search_replace_dict[content.strip()])
                print(f"Modified effect.txt in {root}")


search_replace_pairs = {
    "Choose to not change chosen pizza": "Choose to not change chosen pizza and add it to cart",
    "Choose to add extra cheese to chosen pizza": "Choose to add extra cheese to chosen pizza and add it to cart",
    "Choose option to add item to cart/view/change its options": "Choose to ONE of {add to cart, view/change options}",
    "Choose to ONE of {add to cart, view/change options}": "May be ONE of [add to cart, view/change options], depending on context",
    "May be ONE of [add to cart, view/change options], depending on context": "Depending on accessibility tree, ONE OF {view/change options, OR add to cart}",
}
# Usage
directory_path = 'dominos'
modify_effect_txt(directory_path, search_replace_pairs)