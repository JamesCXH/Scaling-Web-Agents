import os 
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(
                  os.path.dirname(__file__), 
                  os.pardir)
)
sys.path.append(PROJECT_ROOT)



from models.actions import *
from utils.element_utils.element_similarity import element_similarity
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Any
import Levenshtein

PlaywrightPage = Any
CDPSession = Any
AxNode = Any  # TODO: make this a dataclass
@dataclass
class PageState:
    url: str
    ax_nodes: list[AxNode]
    html: str
    actions: list[IndefiniteAction]
    header_html: str
    footer_html: str
    all_tree_lines: list[str]

#represents the union over all possible actions at an exact url
class URLState:
    def __init__(self, url):
        self.aliases : set[str] = {url} #all the urls that are associated with the same action set
        self.unique_samples: dict[str, list[ScrapeAction]] = {} #action set obtainable via any trajectories within this url

    def add_alias(self, url):
        self.aliases.add(url)

    #add sample if no duplicate and return True, otherwise return False
    def add_sample(self, sample: list[ScrapeAction]):
        representative_html = sample[0].action.html
        if representative_html not in self.unique_samples:
            self.unique_samples[representative_html] = sample
            return True
        return False
    #return (for now) percentage of actions from input page_state that can be matched by this urlstate
    def similarity_score(self, page_state : PageState) -> float:
        matched = 0.0
        # print("SIM SCORE INFO")
        # print(len(page_state.actions))
        # print(len([a for a in page_state.actions if a.location == IndefiniteAction.Location.BODY]))
        # input("TAKE A FUCKING LOOK")

        # WE DON'T CONSIDER THE HEADER IN MATCHING OTHER THAN FOR THE HOMEPAGE
        if page_state.url in 'https://www.dominos.com/en/':
            indefinite_actions = page_state.actions
        else:
            indefinite_actions = [a for a in page_state.actions if a.location == IndefiniteAction.Location.BODY]

        total = len(indefinite_actions)

        # if html in footer_html or (html in header_html and url not in 'https://www.dominos.com/en/'):
        #     return IndefiniteAction([], None, nodeId)
        for indefinite_action in indefinite_actions:
            action = indefinite_action.action
            if action.html in self.unique_samples: #attempt O(1) key lookup
                matched += 1
            elif any(element_similarity(action.html, sample_html) > .9 for sample_html in self.unique_samples.keys()):
                matched += 1
        # print(self.aliases)
        if total != 0:
            # print("Similarity score: ", matched / total)
            return matched / total
        else:
            # print("NOTHING HERE TO SCRAPE")
            return 0

    #attempt to match a list of actions and return pairs of actions with matched actions
    def match_actions(self, action_list : list[IndefiniteAction]) -> list[InferenceAction]:
        '''

        @dataclass
        class InferenceAction:
            curr_action: Action
            type_list: list[Action.Type]
            matched_action: Action | None

        @dataclass
        class IndefiniteAction:
            type_list: list[Action.Type]
            action: Action | None

        :param action_list:
        :return:
        '''
        paired_actions = []
        for indefinite_action in action_list:
            action = indefinite_action.action  # aliasing in python is confusing
            max_score = 0
            matched_scrape_action = None
            if indefinite_action.location != IndefiniteAction.Location.FOOTER:  # TODO, we don't try to match for Footer because we never scrape it
                if action.html in self.unique_samples:  # hash check using dictionary, should probably include all scraped htmls instead of representative
                    matched_scrape_sample = self.unique_samples[action.html]  # gets a ScrapeAction
                    for scrape_action in matched_scrape_sample:
                        if scrape_action.action.html == action.html:
                            matched_scrape_action = scrape_action 
                    # resulting_action = InferenceAction(action, indefinite_action.type_list, matched_action, indefinite_action.ax_node_index)
                else:
                    for sample_action_rep_html in self.unique_samples:
                        score = element_similarity(action.html, sample_action_rep_html)
                        if score == 1.0:
                            matched_scrape_sample = self.unique_samples[sample_action_rep_html]
                            min_lev = sys.maxsize
                            min_index = -1 
                            for (i, scrape_action) in enumerate(matched_scrape_sample):
                                curr_lev = Levenshtein.distance(scrape_action.action.html, action.html)
                                if curr_lev < min_lev:
                                    min_lev = curr_lev
                                    min_index = i
                            matched_scrape_action = matched_scrape_sample[min_index]
                            break
                        elif score > max_score:
                            max_score = score
                            if score >= 0.9:
                                matched_scrape_sample = self.unique_samples[sample_action_rep_html]
                                min_lev = sys.maxsize
                                min_index = -1 
                                for (i, scrape_action) in enumerate(matched_scrape_sample):
                                    curr_lev = Levenshtein.distance(scrape_action.action.html, action.html)
                                    if curr_lev < min_lev:
                                        min_lev = curr_lev
                                        min_index = i
                                matched_scrape_action = matched_scrape_sample[min_index]
                    # if matched_scrape_action is None:
                    #     print(max_score)


                if matched_scrape_action:  # NEEDS TO BE BETTER
                    # indefinite_action.action.action_type = matched_scrape_action.action.action_type
                    file_path = matched_scrape_action.before_screenshot
                    file_list = file_path.split('/')
                    file_path = Path ('/'.join(file_list[:-1])) / Path ('effect.txt')
                    numbering = str(file_list[-3]).split(' ')[0]  # TODO, STORE THIS DURING SCRAPE TIME
                    with open(file_path, 'r') as file:
                        content = file.read()
                        matched_scrape_action.action_effect = content
                        matched_scrape_action.number = int(numbering)  # This dependent of folder structuring



            resulting_action = InferenceAction(indefinite_action, matched_scrape_action)
            paired_actions.append(resulting_action)  # WILL APPEND NONE IF NO ACTION HAS SCORE >= 0.9
        return paired_actions

#represents a set of normalized urls
class URLStateManager:
    def __init__(self):
        self.urls : dict[str, URLState] = {}
    def add_url(self, url : str, state : URLState):
        if url not in self.urls:
            self.urls[url] = state
    def get_state(self, page_state : PageState) -> URLState:
        url = page_state.url
        if url in self.urls:
            return self.urls[url]
        else:
            print("GOT HERE")
            max_score = 0
            matched_url_state = None
            for url_state in self.urls.values():
                score = url_state.similarity_score(page_state)
                if score == 1:
                    return url_state
                if score > max_score:
                    max_score = score
                    matched_url_state = url_state
            if max_score >= .70:
                return matched_url_state
            else:
                return None

@dataclass
class InferencePageState:
    url: str
    ax_nodes: list[AxNode]
    html: str
    url_state: URLState
    matched_actions: list[InferenceAction]
    header_html: str
    footer_html: str
    matched: bool
