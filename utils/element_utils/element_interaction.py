import asyncio

async def get_xpath_by_outer_html(page, outer_html):
    # JavaScript function to find the element by outerHTML and generate its XPath
    js_code = """
    (outerHTML) => {
        function getElementXPath(element) {
            if (element.id !== '') {
                return 'id("' + element.id + '")';
            }
            if (element === document.body) {
                return element.tagName.toLowerCase();
            }
            var ix = 0;
            var siblings = element.parentNode.childNodes;
            for (var i = 0; i < siblings.length; i++) {
                var sibling = siblings[i];
                if (sibling === element) {
                    return getElementXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                }
                if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                    ix++;
                }
            }
        }
        var element = Array.from(document.querySelectorAll('*')).find(el => el.outerHTML === outerHTML);
        if (element) {
            return getElementXPath(element);
        }
        return null;
    }
    """
    # Evaluate the JavaScript code in the context of the page
    xpath = await page.evaluate(js_code, outer_html)
    return xpath

async def xpath_from_element(element):
    """
    Derives the XPath of a given Playwright element.

    Args:
        element: Playwright Locator representing the element.

    Returns:
        A string representing the XPath of the element.
    """
    # JavaScript function to compute XPath
    js_get_xpath = """
    (element) => {
        function getXPath(element) {
            if (element.id !== '') {
                return `id("${element.id}")`;
            }
            if (element === document.body) {
                return '/html/body';
            }
            var ix = 0;
            var siblings = element.parentNode.childNodes;
            for (var i = 0; i < siblings.length; i++) {
                var sibling = siblings[i];
                if (sibling === element) {
                    return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + `[${ix + 1}]`;
                }
                if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                    ix++;
                }
            }
        }
        return getXPath(element);
    }
    """
    xpath = await element.evaluate(js_get_xpath)
    return xpath


def remove_last_xpath_item(xpath):
    # Split the string from the right at the last '/'
    parts = xpath.rsplit('/', 1)
    # If there is a '/' in the string, join the parts excluding the last part
    if len(parts) > 1:
        return parts[0]
    # If there is no '/', return the original string
    return xpath

async def click_element_by_outer_html(des_page, outer_html):  # TODO, CLAUDE MORE OF THIS FOR OTHER INTERACTION TYPES
    js_code = """
    (outerHTML) => {
        const element = Array.from(document.querySelectorAll('*')).find(el => el.outerHTML === outerHTML);
        if (element) {
            element.click();
            return true;
        }
        return false;
    }
    """
    result = await des_page.evaluate(js_code, outer_html)
    return result

def make_xpath_friendly(des_xpath):
    if des_xpath:  # if not empty string and not none
        return des_xpath if '(' in des_xpath.split("/")[0] else f"//{des_xpath}"
    else:
        return None

async def get_element(des_page, des_xpath):
    return des_page.locator(f"xpath={des_xpath}") if des_xpath else None