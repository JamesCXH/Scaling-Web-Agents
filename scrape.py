import asyncio
from asyncio import Queue
from asyncio import Lock
import aiofiles
import json
from pathlib import Path
from playwright.async_api import async_playwright, Page, Dialog, TimeoutError
import pickle
# from typing import Optional, Any
from urllib.parse import urlparse, urlunparse
from utils.element_utils.element_similarity import element_similarity
import re
import os
import copy as cp
from scrape_llm import use_gpt_fill_input
import urllib.parse
import shutil
from models import *
from utils import *

"""
there are two relations -- 1. coarse relation 2. fine relation

1. coarse relation
two states relate if their urls normalize the same

2. fine relation
two states relate if their urls are the exact same or...
their actions match above a threshold

the need for the fine relation and explicit action matching has to do with the fact that normalizing is a coarse measure, and 
no method currently exists to properly normalize urls in a way that is consistent with the actions and content of different web pages.

instead, the coarse relation can narrow our search space when there is no exact url match to lessen usage of the computationally expensive action matches
"""
action_number = 1

# this is the aggressive normalization
def normalize_url(url: str) -> str:
    # parsed_url = urlparse(url)
    # scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    # netloc = parsed_url.netloc
    # path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # return urlunparse((scheme, netloc, path, '', '', ''))  # Ignoring the query and fragment
    return url

# out of a set of actions generated from an observation, removes duplicates.
# does not remove duplicates in header or footer because they are generally
# significant enough that we want to keep them
def get_unique_actions(new_state: PageState) -> list[list[IndefiniteAction]]:  # TODO MAKE ASYNC?
    sample_size = 2  # maximum number of samples to include among similar actions
    unique_actions = []
    new_actions = new_state.actions
    header_html = new_state.header_html
    footer_html = new_state.footer_html
    for indefinite_action in new_actions:
        action = indefinite_action.action
        if action.html in header_html or action.html in footer_html:
            unique_actions.append([indefinite_action])  # add header/footer items to own sample
        else:
            unique = True
            for samples in unique_actions:
                if any(element_similarity(action.html, sample_indefinite_action.action.html) >= 0.9 for sample_indefinite_action in samples):
                    # Perhaps add to best match and not first one >= 0.9?
                    if len(samples) < sample_size:
                        samples.append(indefinite_action)
                    unique = False
                    break
            if unique:
                unique_actions.append([indefinite_action])
    return unique_actions

# applies trajectory and returns bool successful
async def apply_trajectory(page: Page, trajectory: List[Action]) -> bool:
    traj_success = True
    if trajectory:
        print("***Executing Trajectory***")
        for traj_action in trajectory:
            await asyncio.sleep(8)
            print('This item now:')
            print(traj_action.tree_line)
            print(traj_action)
            possible_types_traj = [traj_action.action_type]

            traj_element = await get_element(page, traj_action.xpath)
            # assert(traj_action.friendly_xpath != None)

            traj_xpath = traj_action.xpath
            if not traj_element or (await traj_element.count()) < 1 or (await traj_element.evaluate("element => element.outerHTML")) != traj_action.html:
                print('First attempt in traj failed')
                traj_element = await get_element(page, traj_action.friendly_xpath)
                traj_xpath = traj_action.friendly_xpath
                if not traj_element or (await traj_element.count()) < 1 or (await traj_element.evaluate("element => element.outerHTML")) != traj_action.html:
                    print('Second attempt in traj failed')
                    # now we try getting stuff at runtime
                    potentially_better_traj_xpath = await get_xpath_by_outer_html(page, traj_action.html)
                    potentially_better_friendly_traj_xpath = make_xpath_friendly(potentially_better_traj_xpath)
                    traj_element = await get_element(page, potentially_better_friendly_traj_xpath)
                    traj_xpath = potentially_better_friendly_traj_xpath
                    if not traj_element or (await traj_element.count()) < 1:
                        print('Third attempt in traj failed')
                        traj_element = await get_element(page, potentially_better_traj_xpath)
                        traj_xpath = potentially_better_traj_xpath
                        if not traj_element or (await traj_element.count()) < 1:
                            print('Fourth attempt in traj failed')
                            traj_element = await get_element(page, traj_action.friendly_xpath)
                            traj_xpath = traj_action.friendly_xpath
                            if not traj_element or (await traj_element.count()) < 1:
                                print('Fifth attempt in traj failed')
                                traj_element = await get_element(page, traj_action.xpath)
                                traj_xpath = traj_action.xpath

            trajectory_action_screenshot, screenshot_success = await take_screenshot(page)

            if traj_element and (await traj_element.count()) > 0 and traj_xpath:
                try:
                    await scroll_into_view(traj_element)
                    trajectory_action_screenshot, screenshot_success = await take_screenshot(page)
                except Exception as e:
                    print("SCROLL FAILED DURING TRAJECTORY")
                    print(e)

                if screenshot_success:
                    to_box_coords = None
                    try:
                        to_box_coords = await traj_element.bounding_box(timeout=10000)
                    except Exception as e:
                        print(f'GETTING BOUNDING BOXES FAILED FOR IN TRAJ {traj_action}')
                        print(e)

                    trajectory_action_screenshot = await create_boundingbox(trajectory_action_screenshot, to_box_coords)
            else:
                print(f"This action was not found: {traj_action}")
                print('Could not find item in trajectory')

            if not screenshot_success:
                print('traj action screenshot failed')

            success = await apply_action(page, traj_action, trajectory_action_screenshot, traj_element, traj_xpath, possible_types_traj)
            if not success:
                print(f"This action was broken: {traj_action}")
                print("Trajectory broken, skipping")
                traj_success = False
                break

            await wait_for_load(page, load_time_ms=2000)

            if traj_element and (await traj_element.count()) > 0 and traj_xpath:
                traj_action.set_xpath(traj_xpath)
                traj_action.set_friendly_xpath(make_xpath_friendly(traj_xpath))

            await wait_for_load(page, load_time_ms=5000)
        await wait_for_load(page, load_time_ms=5000)
        if not traj_success:
            print('Trajectory failed, here are all its items: ')
            for item in trajectory:
                print(item)
        print("***Finished Executing Trajectory***")
    return traj_success

async def explore_page(url_info: tuple, equiv_classes_lock: Lock, eq_class_lock: Lock,
                      page_queue_lock: Lock,
                      seen_urls_lock: Lock, equiv_classes: URLStateManager, url_queue: Queue, seen_urls: set[str],
                      browser, cookies, root: str, thread_id: str, idle_flags: dict):

    # context = browser.new_context(
    #     user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
    # page = context.new_page()  # instead of making page here, make page in explore_page
    # cdpSession = context.new_cdp_session(page)
    #
    # if cookies is not None:
    #     context.add_cookies(cookies)

    idle_flags[thread_id] = False

    url, url_traj, source_url = url_info
    async with seen_urls_lock:
        if normalize_url(url) in seen_urls:
            return
        seen_urls.add(normalize_url(url))

    # TODO: ROOT MAY TAKE DIFFERENT FORMS, FIX THIS
    def root_check(url_item, root_item):
        parsed_url = urlparse(url_item)
        # return root_item in parsed_url.netloc if parsed_url.netloc else False
        return root_item == parsed_url.netloc if parsed_url.netloc else False

    try:  # this really shouldn't ever fail
        is_in_root = root_check(url, root)
        if not is_in_root:
            print(f"Skipping page outside of root: {url}")
            return
    except:
        print(f"Root check failed, skipping: {url}")
        return

    # we use trajectory to track the sequence of actions needed to trigger the
    # creation of any actions that do not readily exist on the base/unmodified
    # version of the page

    async def explore_actions():
        context, page, cdpSession, login_success = await setup_context(browser, cookies)
        if not login_success:
            print("LOGIN FAILED")
            # close_resources(cdpSession, page, context)
            return
        # if this url has trajectory dependence, we must execute it
        if url_traj:
            print("***Executing url trajectory*** OUTER")
            try:
                await page.goto(source_url)
                await wait_for_load(page, load_time_ms=3000)
            except Exception as e:
                print(f"Error navigating to page during url trajectory: {source_url}. Error: {e}")
                await close_resources(cdpSession, page, context)
                return
            traj_success = await apply_trajectory(page, cp.deepcopy(url_traj))
            if not traj_success:
                print("Failed to execute url trajectory for " + url + "for the first time")
                print(source_url)
                print(url)
                print(page.url)
                await close_resources(cdpSession, page, context)
                return
        else:
            try:
                await page.goto(url)
                await wait_for_load(page, load_time_ms=3000)
            except Exception as e:
                print(f"Error navigating to page: {url}. Error: {e}")
                await close_resources(cdpSession, page, context)
                return

        print("*" * 80)
        print("Want to explore ", url)
        print("Starting from ", source_url)
        await asyncio.sleep(8)

        try:
            root_state = await get_page_state(page, cdpSession)
        except Exception as e:
            print(f"Error getting page state: {url}. Error: {e}")
            await close_resources(cdpSession, page, context)
            return
        # REMEMBER TO HANDLE EQUIVALENCE CLASS CODE - CEM !!!!
        # remember to add a lock
        async with equiv_classes_lock:
            url_state = equiv_classes.get_state(root_state)
            if url_state is None:
                url_state = URLState(url)  # initialize an empty URLState
                equiv_classes.add_url(url, url_state)  # also add a direct link
            else:
                url_state.add_alias(url)  # add this url as an alias to the matched state
                equiv_classes.add_url(url, url_state)  # also add a direct link
                print(url, " is an alias for ", url_state.aliases)
                # cdpSession.detach() #don't forget to close session!
                # page.close()
                # context.close()
                await close_resources(cdpSession, page, context)
                return  # no longer want to scrape the page, TODO CHECK IF MAKES SENSE NEW ACTIONS.ETC

        # seen_actions = []
        # data structure to control flow of new actions
        action_queue = Queue()

        unique_actions = get_unique_actions(root_state)  # should check typing, list of lists of indefinite actions

        # at this point, seen_actions is empty, so we can just put the unique actions into the queue
        for samples in unique_actions:
            await action_queue.put(samples)

        # detach session and close page before while loop
        # cdpSession.detach()
        # page.close()
        # context.close()
        await close_resources(cdpSession, page, context)

        # we can just set seen_actions since it is empty
        # TO IMPROVE EFFICIENCY MAYBE JUST SET THIS TO STRICTLY UNIQUE  - CEM
        # used to check whether an action has already been queued yet (if seen again, we shouldn't requeue)
        seen_actions = unique_actions  # Now a list of IndefiniteAction(s)
        while not action_queue.empty():
            samples = await action_queue.get()
            # samples = action_queue.get(timeout=0.5)  # possible_types should have some sort of importance ordering
            # a samples is a list of indefinite actions
            sample_action_infos: list[ScrapeAction] = []
            for indefinite_sample in samples:

                ###########################################################
                print("-" * 80)
                context, page, cdpSession, login_success = await setup_context(browser, cookies)
                action = indefinite_sample.action
                print("Source page url: ", source_url)
                print("Desired page url: ", url)
                print("Ax object", action.tree_line)
                print("Trajectory: ", action.display_trajectory())

                # do_login(page)  # this should be the only other do_login we need hopefully
                if not login_success:
                    print("LOGIN FAILED")
                    await close_resources(cdpSession, page, context)
                    continue
                if url_traj:
                    try:
                        await page.goto(source_url)
                        await wait_for_load(page, load_time_ms=3000)
                    except Exception as e:
                        print(f"Error navigating to page during url trajectory to source url: {source_url}. Error: {e}")
                        await close_resources(cdpSession, page, context)
                        continue
                    traj_success = await apply_trajectory(page, cp.deepcopy(url_traj))
                    if not traj_success:
                        print("Failed to execute url trajectory on " + page.url + " for the first time")
                        print(source_url)
                        print(url)
                        print(page.url)
                        await close_resources(cdpSession, page, context)
                        continue
                else:
                    try:
                        # url, url_traj, source_url = url_info
                        await page.goto(url)
                        await wait_for_load(page, load_time_ms=3000)
                    except Exception as e:
                        print(f"Error navigating to page: {url}. Error: {e}")
                        await close_resources(cdpSession, page, context)
                        continue
                await asyncio.sleep(4)  # keep just in case lol
                ###########################################################
                possible_types = indefinite_sample.type_list

                # if not action.xpath:  # I may not be the best of checks perhaps
                #     print(f"Skipping action without XPath: {action}")
                #     close_resources(cdpSession, page, context)
                #     continue

                await page.evaluate("""
                    window.print = function() {
                        console.log('Print was triggered');
                    };
                """)

                await asyncio.sleep(6)
                # need sleep here for going between different contexts for some reason

                # print("Action: ", action.html)
                if action.trajectory and action.trajectory != []:
                    print("***Applying Final Action Trajectory***")
                    traj_success = await apply_trajectory(page, action.trajectory)
                    if not traj_success:
                        print("Final action trajectory failed")
                        print(source_url)
                        print(url)
                        print(page.url)
                        print(f"Final action: {action}")
                        await close_resources(cdpSession, page, context)
                        continue

                    print("***Final Action Traj Succeeded***")
                else:
                    print("Final action has no trajectory")

                action.set_friendly_xpath(make_xpath_friendly(action.xpath))

                scroll_success = False

                await asyncio.sleep(8)

                # May want to deepcopy action for safety here
                # print("TRYING TO GET ELEMENT")
                final_element = await get_element(page, action.xpath)
                # print("GOT ELEMENT")
                final_xpath = action.xpath
                if not final_element or (await final_element.count()) < 1 or (await final_element.evaluate("element => element.outerHTML")) != action.html:
                    print('First final element find failed')
                    final_element = await get_element(page, action.friendly_xpath)
                    final_xpath = action.friendly_xpath
                    if not final_element or (await final_element.count()) < 1 or (await final_element.evaluate("element => element.outerHTML")) != action.html:
                        # now we try getting stuff at runtime
                        print('Second final element find failed')
                        potentially_better_xpath = await get_xpath_by_outer_html(page, action.html)
                        potentially_better_friendly_xpath = make_xpath_friendly(potentially_better_xpath)
                        final_element = await get_element(page, potentially_better_friendly_xpath)
                        final_xpath = potentially_better_friendly_xpath
                        if not final_element or (await final_element.count()) < 1:
                            print('Third final element find failed')
                            final_element = await get_element(page, potentially_better_xpath)
                            final_xpath = potentially_better_xpath
                            if not final_element or (await final_element.count()) < 1:
                                print('Fourth final element find failed')
                                final_element = await get_element(page, action.friendly_xpath)
                                final_xpath = action.friendly_xpath
                                if not final_element or (await final_element.count()) < 1:
                                    print('Fifth final element find failed')
                                    final_element = await get_element(page, action.xpath)
                                    final_xpath = action.xpath


                if not final_element or (await final_element.count()) < 1 or not final_xpath:
                    print(f"This element was not found for final {action}")
                    # await close_resources(cdpSession, page, context) TODO JAMES WHY?
                    # continue


                before_screenshot, screenshot_success = await take_screenshot(page)

                if final_element and (await final_element.count()) > 0 and final_xpath:
                    try:
                        await scroll_into_view(final_element)
                        scroll_success = True
                        before_screenshot, screenshot_success = await take_screenshot(page)
                    except Exception as e:
                        print(f'Scroll failed: {e}')

                    if not scroll_success:
                        print(f"Scroll failed for: {final_xpath}, Ax object: {action.tree_line}, outerHTML: {action.html}")
                        # we may still want to try action even if scroll fails throwing playwright error to cause exception, though this is likely due to locator and it's broken

                    if screenshot_success:
                        to_box_coords = None
                        try:
                            # to_box_item = page.locator(f"xpath={action.friendly_xpath}")
                            # if final_element and final_element.count() > 0:  # should be redundant given continue above
                            to_box_coords = await final_element.bounding_box(timeout=10000)
                        except Exception as e:
                            print(f'GETTING BOUNDING BOXES FAILED FOR {action}')
                            print(e)
                        before_screenshot = await create_boundingbox(before_screenshot, to_box_coords)
                else:
                    print("NO PLAYWRIGHT LOCATOR FOR ACTION")

                # print(type(before_screenshot))

                before_state = await get_page_state(page, cdpSession)

                print("ABOUT TO APPLY ACTION")

                success = await apply_action(page, action, before_screenshot, final_element, final_xpath, possible_types)

                print("APPLIED ACTION")

                if not success:
                    print(f"This final action was not successful: {action}")
                    print(f"Attempted types: {possible_types}")
                    # input('Final action failed')
                    await close_resources(cdpSession, page, context)
                    continue  # hopefully no issues with this


                await wait_for_load(page, load_time_ms=2000)

                if final_element and (await final_element.count()) > 0 and final_xpath:
                    action.set_xpath(final_xpath)

                print("THIS ACTION SUCCESSFUL")
                # print(action)

                await wait_for_load(page, load_time_ms=8000)
                if len(page.context.pages) > 1 and page.context.pages[-1] != page:
                    new_page = page.context.pages[-1]
                    after_screenshot, screenshot_success = await take_screenshot(page)
                    if not screenshot_success:
                        print(action)
                        # input('traj action screenshot failed')
                    # after_screenshot = new_page.screenshot(full_page=False)
                    new_page_content = await new_page.content()
                    sample_action_infos.append(ScrapeAction(action, before_state.html, new_page_content, before_screenshot, after_screenshot, url, None, None))
                    async with page_queue_lock:
                        async with seen_urls_lock:
                            if normalize_url(new_page.url) not in seen_urls and root_state.url != page.url:
                                # REMEMBER TO ADD BACK THIS LINE IMMEDIATELY
                                await url_queue.put((new_page.url, [], source_url))  # FOR NOW WE ASSUME NO TRAJ DEPENDENCE FOR THESE
                                #  Make sure everything is discovered, unknown unknowns

                                print(new_page.url)
                    await new_page.close()
                else:
                    after_screenshot, screenshot_success = await take_screenshot(page)
                    if not screenshot_success:
                        print(action)
                        # input('traj action screenshot failed')
                    # after_screenshot = page.screenshot(full_page=False)
                    page_content = await page.content()
                    sample_action_infos.append(ScrapeAction(action, before_state.html, page_content, before_screenshot, after_screenshot, url, None, None))
                # the url is being normalized a bit too aggressively to the point
                # that pages that are clearly different are being put into the same eq
                # because normalized url is the same
                # if normalize_url(before_state.url) != normalize_url(page.url):
                if root_state.url != page.url:
                    async with page_queue_lock:
                        async with seen_urls_lock:
                            if normalize_url(page.url) not in seen_urls:
                                # need to check if the new url has trajectory dependence, or can be directly navigated to
                                url_context, url_page, url_cdpSession, url_login_success = await setup_context(browser, cookies)
                                new_url_trajectory, new_source_url = [], source_url  # changed from None to source_url
                                if url_login_success:
                                    try:
                                        await url_page.goto(page.url)
                                        await wait_for_load(url_page, load_time_ms=8000)
                                        # may need a pagestate check as opposed to a url check, but this is easier for now
                                        if url_page.url != page.url:  # if this is true, this urlstate has trajectory dependence
                                            print("Detected trajectory dependence for ", page.url)
                                            url_trajectory = cp.deepcopy(action.trajectory)  # record trajectory to reach url
                                            url_trajectory.append(action)  # append most recent action
                                            current_url_trajectory = cp.deepcopy(url_traj)  # take trajectory of current url
                                            new_url_trajectory = current_url_trajectory + url_trajectory
                                            new_source_url = root_state.url if source_url is None else source_url  # want to start from the beginning of traj dependence
                                    except Exception as e:
                                        print(f"Error navigating to page: {url_page.url}. Error: {e}")
                                    finally:
                                        # url_cdpSession.detach()
                                        # url_page.close()
                                        # url_context.close()
                                        await close_resources(url_cdpSession, url_page, url_context)
                                await url_queue.put((page.url, new_url_trajectory, new_source_url))  # TODO, IS THIS LOGICALLY CORRECT?
                                print(page.url, new_url_trajectory, new_source_url)
                else:
                    # since we stayed on the same page we want to see if applying
                    # this action generated new content on the page
                    try:
                        await asyncio.sleep(8)
                        new_state = await get_page_state(page, cdpSession)
                        new_actions = get_unique_actions(new_state)
                        # for sample1 in new_actions:
                        #     print("New sample")
                        #     for action1 in sample1:
                        #         print(action1[1].tree_line)
                        #         for seen_sample1 in seen_actions:
                        #             if element_similarity(action1[1].html, seen_sample1[0][1].html) >= .9:
                        #                 print("\t *** Matches to")
                        #                 print("\t ", seen_sample1[0][1].tree_line)
                        # take the set difference unique_actions \ seen_actions
                        # it is fine to just compare one action from each sample, since we assume transitive similarity
                        # seen_actions is all samples, a list of lists of indefinite actions
                        # a seen_sample is a list of indefinite actions
                        difference = [sample for sample in new_actions if all(element_similarity(sample[0].action.html, seen_sample[0].action.html) < .9 for seen_sample in seen_actions)]
                        # put the difference onto the queue
                        new_trajectory = []
                        if difference:
                            new_trajectory = cp.deepcopy(action.trajectory)
                            new_trajectory.append(action)
                            print("***Detected new actions***")
                        for sample in difference:  # each sample is a list of indefinite actions
                            print("New sample")
                            # for dTl, different_action in sample:
                            for indefinite_action in sample:
                                print("\tNew action: ", indefinite_action.action.tree_line)
                                # update trajectory with parent's trajectory + parent
                                indefinite_action.action.set_trajectory(new_trajectory)
                            await action_queue.put(sample)
                        # put the difference into the seen_actions, effectively unique_actions U seen_actions
                        seen_actions += difference
                    except Exception as e:
                        print(f"Error getting page state after applying {action.tree_line} at {url}. Error: {e}")
                        await close_resources(cdpSession, page, context)
                        continue
                # cdpSession.detach()
                # page.close()
                # context.close()
                await close_resources(cdpSession, page, context)

            if sample_action_infos:  # the only reason sample_action_infos may be empty is if the action errored out and never got added
                global action_number
                async with eq_class_lock:
                    if url_state.add_sample(sample_action_infos):  # proceed if this is a new action
                        # folder saving code
                        output_dir = 'dominos_dep'
                        action_info = sample_action_infos[0]
                        tree_string = action_info.action.tree_line
                        tree_string = tree_string if len(tree_string) <= 40 else tree_string[:40]
                        cleaned_url = re.sub(r'^(https?://)?(www\.)?', '', action_info.url)
                        cleaned_url = cleaned_url.rstrip('/')
                        sample_path = Path(output_dir) / Path(urllib.parse.quote(cleaned_url, safe='')) / Path(str(action_number) + ' ' + tree_string)  # root / url / action, make new url folder if it doesn't exist
                        sample_path.mkdir(parents=True, exist_ok=True)
                        for num, action_info in enumerate(sample_action_infos):
                            tree_string = action_info.action.tree_line
                            tree_string = tree_string if len(tree_string) <= 40 else tree_string[:40]
                            subdir_path = sample_path / Path(str(num))
                            subdir_path.mkdir(parents=True, exist_ok=True)
                            before_screenshot_filename = f"action_{hash(action_info.action.html)}_before.png"
                            before_screenshot_path = subdir_path / before_screenshot_filename
                            with open(before_screenshot_path, 'wb') as f:
                                f.write(action_info.before_screenshot)
                            action_info.before_screenshot = str(before_screenshot_path)

                            after_screenshot_filename = f"action_{hash(action_info.action.html)}_after.png"
                            after_screenshot_path = subdir_path / after_screenshot_filename
                            with open(after_screenshot_path, 'wb') as f:
                                f.write(action_info.after_screenshot)
                            action_info.after_screenshot = str(after_screenshot_path)

                            with open(Path(subdir_path) / 'info.txt', 'w') as f:
                                f.write(f"URL: {action_info.url}\n")
                                f.write(f"TREE LINE: {action_info.action.tree_line}\n")
                                f.write(f"XPATH: {action_info.action.friendly_xpath}\n")
                                f.write(f"TRAJECTORY: {action_info.action.trajectory}\n\n")
                                f.write(f"HTML: {action_info.action.html}\n")
                action_number += 1

        # NEED TO ACTUALLY UPDATE THE ACTIONS, THEY ARE ONLY ADDED AT THE BEGINNING - Cem

    await explore_actions()
    output_dir = 'dominos_dep'
    output_path = Path(output_dir) / 'scraper_state.pkl'
    checkpoint_path = Path(output_dir) / 'checkpoint.pkl'

    urls = list(url_queue._queue)  # Accessing the protected member _queue

    async with aiofiles.open(output_path, 'wb') as f:
        await asyncio.to_thread(pickle.dump, equiv_classes, f)  # Run pickle.dump in a thread
    async with aiofiles.open(checkpoint_path, 'wb') as f:
        await asyncio.to_thread(pickle.dump, (action_number, urls, seen_urls), f)

    print("Saved checkpoint")

    # special_output_path = Path('special_dominos') / 'special_scraper_state.pkl'
    # special_checkpoint_path = Path('special_dominos') / 'special_checkpoint.pkl'
    #
    # if urls != [] and 'www.dominos.com/en/pages/order/#!/checkout' in urls[0][0]:
    #     print("Saved special checkpoint")
    #     with open(special_output_path, 'wb') as f:
    #         pickle.dump(equiv_classes, f)  # url_queue and current url needed for resume purposes
    #     with open(special_checkpoint_path, 'wb') as f:
    #         pickle.dump((action_number, urls, seen_urls), f)

    if url_queue.empty() and url_queue.qsize() <= 0:
        idle_flags[thread_id] = True

async def worker(thread_id: str, idle_flags: dict, url_queue: Queue, equiv_classes_lock: Lock, eq_class_lock: Lock, page_queue_lock: Lock, seen_urls_lock: Lock, equiv_classes, seen_urls: set[str], headless: bool, cookies: Optional[dict], root: str, stop_event: asyncio.Event):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        # context = browser.new_context(
        #     user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        # page = context.new_page()  # instead of making page here, make page in explore_page
        # cdpSession = context.new_cdp_session(page)

        # if cookies is not None:
        #     context.add_cookies(cookies)

        while not stop_event.is_set():
            url_info = None
            try:
                url_info = await asyncio.wait_for(url_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                idle_flags[thread_id] = True
                continue

            if url_info is not None:
                await explore_page(url_info, equiv_classes_lock, eq_class_lock, page_queue_lock, seen_urls_lock, equiv_classes,
                                  url_queue, seen_urls, browser, cookies, root, thread_id, idle_flags)
                await asyncio.sleep(4)
                url_queue.task_done()
            else:
                idle_flags[thread_id] = True
            if stop_event.is_set():
                break

            await asyncio.sleep(4)

        print(f"worker Thread-{thread_id} dying")
        await browser.close()

async def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False, output_dir: str = 'dominos_dep', root: str = "", num_threads: int = 10, resume: bool = False):
    global action_number
    # Initialize an EquivalenceClassSet to store and manage equivalence classes
    scraper_state_path = Path(output_dir) / 'scraper_state.pkl'
    checkpoint_path = Path(output_dir) / 'checkpoint.pkl'
    if resume and scraper_state_path.exists() and checkpoint_path.exists():
        # async with aiofiles.open(scraper_state_path, 'rb') as f:
        #     equiv_classes = await asyncio.to_thread(pickle.load, f)
        # async with aiofiles.open(checkpoint_path, 'rb') as f:
        #     resumed_action_number, urls, seen_urls = await asyncio.to_thread(pickle.load, f)
        async with aiofiles.open(scraper_state_path, 'rb') as f:
            equiv_classes = pickle.loads(await f.read())
        async with aiofiles.open(checkpoint_path, 'rb') as f:
            resumed_action_number, urls, seen_urls = pickle.loads(await f.read())
        action_number = resumed_action_number
        url_queue = Queue()
        for url_info in urls:
            await url_queue.put(url_info)
        # remove partially filled urlstate
        cleaned_url = re.sub(r'^(https?://)?(www\.)?', '', urls[0][0])
        cleaned_url = cleaned_url.rstrip('/')
        old_urlstate_path = Path(output_dir) / urllib.parse.quote(cleaned_url, safe='')
        if old_urlstate_path.exists():
            shutil.rmtree(old_urlstate_path)
            print("Removed partially explored urlstate")
        print("Resuming exploration from ", urls[0][0])
    else:
        if resume:
            print("Couldn't find checkpoint and state files for resume. Starting from scratch")
        equiv_classes: URLStateManager = URLStateManager()

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        seen_urls = set()

        url_queue = Queue()
        await url_queue.put((starting_url, [], None))

    equiv_classes_lock = Lock()
    eq_class_lock = Lock()
    stop_event = asyncio.Event()
    page_queue_lock = Lock()
    seen_urls_lock = Lock()

    threads = []
    idle_flags = {}
    for i in range(num_threads):
        thread_id = f"Thread-{i}"
        idle_flags[thread_id] = False
        t = asyncio.create_task(worker(
            thread_id, idle_flags, url_queue, equiv_classes_lock, eq_class_lock, page_queue_lock,
            seen_urls_lock, equiv_classes, seen_urls,
            headless, cookies, root, stop_event))
        threads.append(t)

    while True:
        if url_queue.empty() and all(idle_flags[i] for i in idle_flags) and url_queue.qsize() <= 0:
            await asyncio.sleep(4)
            stop_event.set()
            break
        else:
            await asyncio.sleep(4)

    await asyncio.gather(*threads)

    # Save the EquivalenceClassSet object using pickling

    print(url_queue.qsize())
    print(seen_urls)

num_cores = os.cpu_count()
if __name__ == "__main__":
    asyncio.run(explore("https://www.dominos.com/", headless=False, root="www.dominos.com", num_threads=1, resume=False))
