from __future__ import annotations
import os 
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(
                  os.path.dirname(__file__), 
                  os.pardir)
)
sys.path.append(PROJECT_ROOT)
from models.states import InferencePageState
from models.actions import *
import re 
from abc import ABC, abstractmethod
class PageObservation(ABC):

    # observations can be compared
    @abstractmethod
    def __eq__(self, other : PageObservation) -> bool:
        pass
class AxObservation(PageObservation):
    def __init__(self, axtree, url, processed = True, numbered = True):
        self.axtree = axtree
        self.url = url
        self.numbered = numbered
        node_id_to_idx = {}
        for idx, node in enumerate(self.axtree):
            node_id_to_idx[node["nodeId"]] = idx  # NOW WE HAVE A NEW ID SYSTEM, GOES UP EASIER FOR BOT

        self.nodes_info = []
        def dfs(idx: int, obs_node_id: str, depth: int) -> str:
            pua_cleaner = re.compile('[\ue000-\uf8ff]')
            node = self.axtree[idx]
            indent = "\t" * depth
            valid_node = True
            try:
                role = node["role"]["value"]
                name = node["name"]["value"]
                name = pua_cleaner.sub('', name)
                properties = []
                for property in node.get("properties", []):
                    try:
                        ignored_properties = {"focusable", "editable", "readonly", "level", "settable", "multiline", "invalid"}
                        if property["name"] in ignored_properties:
                            continue
                        elif property["name"] == "hidden" and property["value"]["value"]:
                            if not processed:
                                continue 
                            valid_node = False
                            break
                        properties.append(f'{property["name"]}: {property["value"]["value"]}')
                    except KeyError:
                        pass
                # check valid
                if not role and not name.strip():
                    valid_node = False

                # empty generic node
                if not name.strip():
                    # if not properties:
                    if role in ["generic", "img", "list", "strong", "paragraph", "banner", "navigation", "Section",
                                "LabelText", "Legend", "listitem", "LineBreak", "ListMarker", "gridcell", "link"]:  # TODO, double check logic, I did this arbitrarily ripping things out
                        valid_node = False
                    # elif role in ["listitem"]:
                    #     include_in_nodes_info = False

                if valid_node:
                    node_info = {
                        "nodeId": obs_node_id,  #LATER CHANGED AFTER DFS
                        "name": name,
                        "role": role,
                        "indent": indent,
                        "properties": properties,
                        "html": node['html'] if 'html' in node else "",  # MUST BE EMPTY STRING OR MAY BREAK AX NODE TO ACTION CODE
                        "xpath": node['xpath'] if 'html' in node else "",
                        "parent_html": node['parent_html'] if 'parent_html' in node else ""
                    }
                    self.nodes_info.append(node_info)



            except Exception as e:
                valid_node = False

            for _, child_node_id in enumerate(node["childIds"]):
                if child_node_id not in node_id_to_idx:
                    continue
                # mark this to save some tokens
                child_depth = depth + 1 if valid_node else depth
                dfs(node_id_to_idx[child_node_id], child_node_id, child_depth)

        dfs(0, self.axtree[0]["nodeId"], 0)
        """further clean accesibility tree"""
        cleaned_nodes = []
        # node_id_counter = 0
        for node in self.nodes_info:
            # remove statictext if the content already appears in the previous line
            if node["role"] == "StaticText":
                prev_nodes = cleaned_nodes[-3:]
                found = False
                for prev in prev_nodes:
                    if node["name"] in prev["name"]:
                        found = True
                if found:
                    continue
            # node["nodeId"] = node_id_counter  # RESETS NODE IDs TO BE ENUMERATED
            # node_id_counter += 1
            cleaned_nodes.append(node)
        self.nodes_info = cleaned_nodes

    def __eq__(self):
        pass

    def __str__(self):
        tree_str = ''
        if self.numbered:
            for node in self.nodes_info:
                tree_str += f"{node['indent']}[{node['nodeId']}] {node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        else:
            for node in self.nodes_info:
                tree_str += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        return tree_str

class InferenceAxtree:

    #  we get axnodes which we roll into a pagestate, which we will roll into an InferencePageState, which we will then reroll into a InferenceAxtree
    #  TODO give header and footer actions
    """

    VERY IMPORTANT: THERE CAN BE NO MATCHED SCRAPE IN scrape_info, i.e., scrape_info.url_state CAN BE NONE.


    """
    def __init__(self, scrape_info: InferencePageState, special_actions = None, use_scrape = True, url = ''):
        self.scrap_info = scrape_info
        self.action_effect_lib = dict()
        self.action_lib = dict()
        self.action_number_lib = dict()
        self.action_tree_lines = dict()
        self.use_scrape = use_scrape
        self.live_actions = []
        self.live_action_effects = []
        self.special_actions = special_actions if special_actions is not None else []
        self.url = url

        count = 0
        self.raw_tree = ''
        self.scrape_tree = ''
        self.scrape_tree_no_special = ''
        self.action_tree_no_scrape = ''
        self.debug_tree = ''
        self.input_tree = ''

        # input_all_action = Action(Action.Type.INPUT_GIVEN_INTENT, None, None)
        # input_all_action.set_special_effect(
        #     'Call an agent to fill in all inputs on the page given some intent. {The intent is action_reason you return in choose}')
        # input_all_indefinite = IndefiniteAction([Action.Type.INPUT_GIVEN_INTENT], input_all_action, None,
        #                                         IndefiniteAction.Location.SPECIAL)

        # self.raw_tree += f"[{count}] SPECIAL ACTION: {str(input_all_indefinite.action.special_effect)}\n"
        # self.scrape_tree += f"[{count}] SPECIAL ACTION: {str(input_all_indefinite.action.special_effect)}\n"
        # self.debug_tree += f"[{count}] SPECIAL ACTION: {str(input_all_indefinite.action.special_effect)}\n"
        # self.live_actions.append(input_all_indefinite)
        # self.live_action_effects.append("SPECIAL ACTION")
        # count += 1

        for indefinite_action in self.special_actions:
            # self.raw_tree += f"SPECIAL ACTION: {str(indefinite_action.action.special_effect)}\n"  # SAVE TOKENS
            self.scrape_tree += f"[{count}] SPECIAL ACTION: {str(indefinite_action.action.special_effect)}\n"
            self.debug_tree += f"[{count}] SPECIAL ACTION: {str(indefinite_action.action.special_effect)}\n"
            self.action_tree_lines[count] = f"SPECIAL ACTION: {str(indefinite_action.action.special_effect)}"
            if indefinite_action.action.action_type == Action.Type.REQUEST_USER_INPUT:
                self.input_tree += f"[{count}] SPECIAL ACTION: {str(indefinite_action.action.special_effect)}\n"
            self.live_actions.append(indefinite_action)
            self.live_action_effects.append("SPECIAL ACTION")
            count += 1

        for attempted_match in scrape_info.matched_actions:
            curr_action = attempted_match.curr_action
            scraped_action = attempted_match.matched_scrape_action
            if scraped_action:
                action_effect = scraped_action.action_effect
                if action_effect is None:
                    # TODO: does this ever happen???
                    # action_effect = curr_action.action.tree_line
                    action_effect = ''  # matched in found url state but it somehow doesn't have an action effect
                numbering = scraped_action.number
            else:
                numbering = '-1'
                # action_effect = curr_action.action.tree_line
                action_effect = ''  # not matched in found url state we don't give an action effect
            self.action_effect_lib[curr_action.ax_node_index] = action_effect
            self.action_number_lib[curr_action.ax_node_index] = numbering
            self.action_lib[curr_action.ax_node_index] = curr_action



        # NOTE: ASSUMES SPECIAL ACTION OF INPUT ALL ALWAYS EXISTS
        if not self.use_scrape:
            for node in self.scrap_info.ax_nodes:
                # if node['html'] in scrape_info.footer_html:
                #     break
                if node['nodeId'] in self.action_effect_lib:
                    # if self.action_lib[node['nodeId']].location == IndefiniteAction.Location.FOOTER:
                    #     break
                    if Action.Type.INPUT in self.action_lib[node['nodeId']].type_list and self.action_lib[node['nodeId']].location != IndefiniteAction.Location.FOOTER:
                        self.raw_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.debug_tree += f"[{count}; WRITE_TEXT] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.input_tree += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.action_tree_lines[count] = f"WRITE_TEXT; {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"])
                        self.action_tree_no_scrape += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                    else:
                        self.raw_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.debug_tree += f"[{count}] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.input_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                        self.action_tree_lines[count] = f"{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"])
                        self.action_tree_no_scrape += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"

                    count += 1
                    self.live_actions.append(self.action_lib[node['nodeId']])
                    self.live_action_effects.append(self.action_effect_lib[node['nodeId']])
                else:
                    self.raw_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.debug_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.input_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.action_tree_no_scrape += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
        else:
            for node in self.scrap_info.ax_nodes:
                # if node['html'] in scrape_info.footer_html:
                #     break
                if node['nodeId'] in self.action_effect_lib and self.action_lib[node['nodeId']].location != IndefiniteAction.Location.FOOTER:
                    if Action.Type.INPUT in self.action_lib[node['nodeId']].type_list:
                        self.scrape_tree += f"{node['indent']}[{count}; WRITE_TEXT] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + "\n"
                        self.scrape_tree_no_special += f"{node['indent']}[{count}; WRITE_TEXT] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + "\n"
                        self.raw_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.debug_tree += f"[{count}; WRITE_TEXT] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + f" **MATCHED TO {self.action_number_lib[node['nodeId']]}**" + "\n"
                        self.input_tree += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + "\n"
                        self.action_tree_lines[count] = f"WRITE_TEXT; {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"])
                        self.action_tree_no_scrape += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                    else:
                        self.scrape_tree += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + "\n"
                        self.scrape_tree_no_special += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + "\n"
                        self.raw_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.debug_tree += f"[{count}] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + " {" + self.action_effect_lib[node[
                            'nodeId']] + "}" + f" **MATCHED TO {self.action_number_lib[node['nodeId']]}**" + "\n"
                        self.input_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"
                        self.action_tree_lines[count] = f"{node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"])
                        self.action_tree_no_scrape += f"{node['indent']}[{count}] {node['role']} {repr(node['name'])} " + " ".join(
                            node["properties"]) + "\n"

                    count += 1
                    self.live_actions.append(self.action_lib[node['nodeId']])
                    self.live_action_effects.append(self.action_effect_lib[node['nodeId']])
                else:
                    self.debug_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.raw_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.scrape_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.scrape_tree_no_special += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.input_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.action_tree_no_scrape += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"




    def get_action_from_index(self, index: int) -> IndefiniteAction:
        return self.live_actions[index]

    def get_debug_tree(self):
        return self.debug_tree

    def get_action_effect_from_index(self, index: int) -> str:
        return self.live_action_effects[index]

    def get_question_tree(self):
        if self.action_tree_no_scrape != "":
            return self.action_tree_no_scrape
        return self.raw_tree

    def get_input_tree(self):
        return self.input_tree
    def get_action_treelines(self, indices):
        new_indices = sorted(list(set(indices)))
        return [self.action_tree_lines[i] for i in new_indices]
    def get_tree_with_specific_action_effect(self, indices: List[int]) -> str:

        target_actions = [self.live_actions[i] for i in indices]
        target_action_ax_node_indices = [target_action.ax_node_index for target_action in target_actions]
        # Retrieve the target action and its effect
        # target_action = self.live_actions[index]

        tree_str = ''
        count = 0

        # Iterate over special actions first
        for i, special_action in enumerate(self.special_actions, start=0):  # just to keep indexing consistent, but save tokens
        #     if count in indices:
        #         # Include the action effect
        #         tree_str += f"[{count} (THIS ACTION WAS JUST CHOSEN)] SPECIAL ACTION: {str(special_action.action.special_effect)}\n"
        #     else:
        #         # Omit the action effect
        #         tree_str += f"[{count}] SPECIAL ACTION: \n"
            count += 1

        # Iterate over ax_nodes
        for node in self.scrap_info.ax_nodes:
            node_id = node['nodeId']
            if node_id in self.action_effect_lib and self.action_lib[node_id].location != IndefiniteAction.Location.FOOTER:
                action = self.action_lib[node_id]
                action_effect = self.action_effect_lib[node_id]

                if node_id in target_action_ax_node_indices:
                    # Include the action effect
                    if Action.Type.INPUT in action.type_list:
                        tree_str += (
                            f"[{count} (JUST INPUT)] {node['indent']}"
                            f"{node['role']} {repr(node['name'])} "
                            f"{' '.join(node['properties'])} {{{action_effect}}}\n"
                        )
                    else:
                        tree_str += (
                            f"[{count} (JUST CHOSEN)] {node['indent']}"
                            f"{node['role']} {repr(node['name'])} "
                            f"{' '.join(node['properties'])} {{{action_effect}}}\n"
                        )
                else:
                    # Omit the action effect
                    if Action.Type.INPUT in action.type_list:
                        # tree_str += (
                        #     f"[{count}; WRITE_TEXT] {node['indent']}"
                        #     f"{node['role']} {repr(node['name'])} "
                        #     f"{' '.join(node['properties'])}\n"
                        # )
                        tree_str += (
                            f"{node['indent']}"
                            f"{node['role']} {repr(node['name'])} "
                            f"{' '.join(node['properties'])}\n"
                        )
                    else:
                        # tree_str += (  # SAVE TOKENS
                        #     f"[{count}] {node['indent']}"
                        #     f"{node['role']} {repr(node['name'])} "
                        #     f"{' '.join(node['properties'])}\n"
                        # )
                        tree_str += (
                            f"{node['indent']}"
                            f"{node['role']} {repr(node['name'])} "
                            f"{' '.join(node['properties'])}\n"
                        )

                # Append to live_actions and live_action_effects is not needed here
                count += 1
            else:
                # Nodes without associated actions are added as-is
                tree_str += (
                    f"{node['indent']}{node['role']} {repr(node['name'])} "
                    f"{' '.join(node['properties'])}\n"
                )

        return tree_str

    def get_raw_tree(self):
        return self.raw_tree

    def get_scrape_tree(self):
        return self.scrape_tree

    def get_no_special(self):
        if self.use_scrape:
            return self.scrape_tree_no_special
        return self.raw_tree

    def __str__(self):
        if self.use_scrape:
            return self.scrape_tree
        return self.raw_tree