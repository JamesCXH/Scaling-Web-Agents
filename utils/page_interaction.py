import time
from models.accessbility import *
from models.states import *
from utils.web_extraction import *
from utils.element_utils.element_interaction import *
import numpy as np
from scrape_llm import use_gpt_fill_input
# import cv2
from typing import Optional, List, Any


async def login(page):
    # print('LOGGING IN')
    await page.goto('https://www.dominos.com/en/restaurants?type=Carryout')
    await wait_for_load(page)
    # await page.get_by_label("Street Address", exact=False).fill('934 Keeamoku Street')
    # await page.get_by_label("Suite/Apt #", exact=False).fill('')
    # await page.get_by_label("ZIP Code", exact=False).fill('96814')
    # await page.get_by_label("City", exact=False).fill('Honolulu')
    # await page.get_by_label("State", exact=False).select_option('HI')
    # await page.get_by_label("Street Address", exact=False).fill('5819 Centre Ave')
    # await page.get_by_label("Suite/Apt #", exact=False).fill('Apt 448')
    # await page.get_by_label("ZIP Code", exact=False).fill('15206')
    # await page.get_by_label("City", exact=False).fill('Pittsburgh')
    # await page.get_by_label("State", exact=False).select_option('PA')  # THIS
    # await page.get_by_label("Street Address", exact=False).fill('5000 Forbes Ave')
    # await page.get_by_label("ZIP Code", exact=False).fill('15213')
    await page.get_by_label("City", exact=False).fill('Pittsburgh')
    await page.get_by_label("State", exact=False).select_option('PA')  # THIS
    await page.get_by_role("button", name="Find a Store").click()
    await wait_for_load(page)
    # await page.get_by_role("button", name="Delivery To").click()
    # await page.get_by_role("button", name="Change").click()
    # await page.get_by_role("button", name="Carryout").click()
    first_item = page.get_by_role("link", name="Store Pickup").nth(1)
    await first_item.click()
    await wait_for_load(page)

async def setup_context(browser, cookies, logged_in = True, attempts = 3):
    context, page, cdpSession = await create_new_context_and_page(browser, cookies)
    success = True
    if logged_in:
        for attempt in range(attempts):
            try:
                if not success: #if we failed before, create new context and page
                    context, page, cdpSession = await create_new_context_and_page(browser, cookies)
                    print("Trying login again...")
                await login(page)
                # print('LOGIN SUCCESSFUL')
            except Exception as e:
                # page.screenshot(path='login_failure.png', full_page=True)
                await close_resources(cdpSession, page, context)
                
                print(f"Error logging in {attempt+1} times: {e}")
                success=False
            else:
                success = True
                break
    return context, page, cdpSession, success

async def create_new_context_and_page(browser, cookies):
        context = await browser.new_context(
            permissions=[], #this is to prevent popups
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        if cookies is not None:
            await context.add_cookies(cookies)
        page = await context.new_page()
        cdpSession = await context.new_cdp_session(page)
        return context, page, cdpSession

async def close_resources(cdp_session, page, context):
    await cdp_session.detach()
    await page.close()
    await context.close()

async def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    await page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    await page.wait_for_timeout(load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race

async def get_page_state(page: PlaywrightPage, cdpSession: CDPSession, attempts=3, delete_footer=True) -> PageState:
    result = None

    for _ in range(attempts):
        # Navigate to the given URL and wait for the page to load
        start = time.time()
        #wait_for_load(page)

        if delete_footer:
            remove_footer_js = """
            () => {
              const footer = document.querySelector('footer');
              if (footer) {
                footer.remove();
              }
            }
            """
            await page.evaluate(remove_footer_js)

        # print("Load took", time.time() - start)
        # Retrieve the accessibility tree and create an AxObservation object
        start = time.time()
        ax_nodes = await get_ax_tree(cdpSession)
        # print("CDP took", time.time() - start)
        start = time.time()
        cleaned = AxObservation(ax_nodes, page.url)  # LITERALLY THE WHOLE TREE
        # print("Cleaning took", time.time() - start)
        #DON'T PRINT FOR NOW, IT'S CLUTTERING EVERYTHING

        # Extract the header and footer HTML
        start = time.time()
        header_html = await page.evaluate("document.getElementsByTagName('header')[0]?.outerHTML || ''")
        footer_html = await page.evaluate("document.getElementsByTagName('footer')[0]?.outerHTML || ''")
        # header_html = ''
        # print("Header footer took", time.time() -start)
        #currently page specific

        # Extract actions from the accessibility nodes and filter out None values, only scrape header and footer on homepage
        # actions = [ax_node_to_action(node, header_html if page.url not in 'https://www.dominos.com/en/' else '', footer_html if page.url not in 'https://www.dominos.com/en/' else '') for node in cleaned.nodes_info]
        '''
        
        IMPORTANT: ACTIONS FROM CLEANED AND NOT RAW AX_NODES!!!
        SO EVERYTHING ACTUALLY IS IN VIEWABLE TREE!!!
        
        '''
        start = time.time()
        indefinite_actions = [ax_node_to_action(node, header_html, footer_html, page.url) for node in cleaned.nodes_info]
        # print("LENGTH: ", len(indefinite_actions))
        # print("Converting to actions took ", time.time() - start)
        new_indefinite_actions = []
        start = time.time()
        for indefinite_action in indefinite_actions:
            if (indefinite_action is not None) and (indefinite_action.action is not None) and (indefinite_action.type_list != []):
                new_indefinite_actions.append(indefinite_action)
        # print("NEW LENGTH", len(new_indefinite_actions))
        # print("Indefinite action loop took", time.time() - start)
        # indefinite_actions = [(tL, a) for (tL, a) in indefinite_actions if tL != []]  # TODO now a list of lists of actions


        # Create and return a PageState object with the normalized URL, HTML content, actions, header HTML, and footer HTML


        result = PageState(
            url=page.url,
            ax_nodes=cleaned.nodes_info,  # note now this nodes info is the cleaned version of nodes that we get out of AxObservation
            html= await page.content(),
            actions=new_indefinite_actions,
            header_html=header_html,
            footer_html=footer_html,
            all_tree_lines=[a.action.tree_line for a in new_indefinite_actions if a.action is not None]
        )
        if len(result.actions) > 0:
            return result

    return result

async def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, playwright_element, found_xpath=None, possible_types=None) -> bool:  # TODO handle multiple possible action types
    for a_type in possible_types:
        try:
            if a_type in [Action.Type.CLICK_LINK, Action.Type.CLICK_IMPORTANT, Action.Type.CLICK_CHECKBOX,
                               Action.Type.CLICK_RADIO, Action.Type.CLICK_GENERAL]:
                count = await playwright_element.count()
                if count > 0:
                    try:
                        await page.evaluate(
                            f"() => {{ let e = document.evaluate('{found_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
                        a.action_type = a_type  # probs not good
                        return True
                    except Exception as e:
                        print(f"Error clicking element via JavaScript click: {e}")

                    try:
                        await playwright_element.click(timeout=5000)
                        a.action_type = a_type
                        return True
                    except Exception as e:
                        print(f"Error clicking element via Playwright locator.click: {e}")
                try:
                    outer_html_click_success = await click_element_by_outer_html(page, a.html)
                    if outer_html_click_success:
                        a.action_type = a_type
                        return True
                except Exception as e:
                    print(f"Error clicking element via OuterHTML {e}")

            elif a_type == Action.Type.SELECT_GENERAL:
                count = await playwright_element.count()
                if count > 0 or found_xpath:
                    try:
                        await page.evaluate(f"""
                                (xpath) => {{
                                    const option = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                    if (option) {{
                                        option.selected = true;
                                        const event = new Event('change', {{ bubbles: true }});
                                        option.parentElement.dispatchEvent(event);
                                    }}
                                }}
                            """, found_xpath)
                        a.action_type = a_type
                        return True
                    except Exception as e:
                        print(f"Error selecting element via Javascript: {e}")

                    try:
                        friendly_xpath = remove_last_xpath_item(found_xpath)  # overrides, may be broken after change which makes apply action use playwright objects
                        found_item = await page.locator(f"xpath={friendly_xpath}")
                        await found_item.select_option(a.desired_option.strip(), timeout=5000)
                    except Exception as e:
                        print(f"Error selecting element via Playwright and trimmed xpath: {e}")

            elif a_type == Action.Type.INPUT:
                count = await playwright_element.count()
                if count > 0:
                    try:
                        await playwright_element.fill(a.input_string, force=True, timeout=5000)
                        a.action_type = a_type
                        return True
                    except Exception as e:
                        print(f"Error inputting text into element: {e}")
                else:
                    print("Can't input into nothing")

            elif a_type == Action.Type.GOTO_URL:
                try:
                    await page.goto(a.input_string, timeout=5000)
                    # page.wait_for_load_state('networkidle', timeout=5000)
                    a.action_type = a_type
                    return True
                except Exception as e:
                    print(f"Error navigating to URL: {e}")

            elif a_type == Action.Type.GO_BACK:
                pass
                # try:
                #     page.go_back(), timeout=5000
                #     page.wait_for_load_state('networkidle', timeout=5000)
                #     return True, action_type
                # except Exception as e:
                #     print(f"Error going back: {e}")
                await page.goto(a.input_string)
                await page.wait_for_load_state('networkidle')

        except Exception as e:
            print(f"Unhandled exception for action type {a_type}: {e}")

    return False

async def take_screenshot(page, attempts=3, full=False):
    for i in range(attempts):
        try:
            screenshot = await page.screenshot(full_page=full)
            return screenshot, True
        except Exception as e:
            print("SCREENSHOT FAILED")
            print(e)
    return None, False