#!/usr/bin/env python3

import sys

if sys.version_info[0] != 3:
    if __name__ == '__main__':
        sys.exit("This is a python3 script, it looks like you are using python" + str(sys.version_info[0]) + '.')
    else:
        raise ImportError("This is a python3 module")

import argparse, os, getpass, http.cookiejar, urllib.request, re, json, time

try:
    from bs4 import BeautifulSoup
except ImportError as e:
    if __name__ == '__main__':
        print("This program requires the BeautifulSoup module for parsing HTML")
        print("It can be installed from: http://www.crummy.com/software/BeautifulSoup/")
        sys.exit(1)
    else:
        raise

    
def get_user_pass(username=None):
    """ Just get the login details from the user """

    if username == None:
        username = input("Username: ")

    password = getpass.getpass()

    return (username, password)


def create_uniq_folder(dir_path):
    """ Create unique folder and return it's path """

    temp_dir = dir_path

    i = 1
    while (os.path.exists(temp_dir)):
        temp_dir = dir_path + '_' + str(i)
        i = i + 1 

    dir_path = temp_dir
    os.mkdir(dir_path)

    return dir_path


def get_uniq_valid_filename(filepath, filename):
    """ Sanitise and ensure unique """ 

    invalid = '[<>:"/\|?*\x00]'
    
    filename = re.sub(invalid, '', filename)
    filename = os.path.join(filepath, filename)

    temp_filename = filename

    i = 1
    while (os.path.exists(temp_filename)):
        extsplit = os.path.splitext(filename)
        temp_filename = extsplit[0] + '_' + str(i) + extsplit[1]
        i = i + 1 

    filename = temp_filename

    return filename


def bebo_login(user, passwd):
    """ Login and return error and url opener to handle all our cookies etc. """
    
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        #opener.open("http://www.bebo.com")  # Load some session cookies 
        opener.open("https://secure.bebo.com")  # Load some session cookies 
    except (urllib.error.HTTPError, urllib.error.URLError):
        return (1, None) 

    data = urllib.parse.urlencode( {'EmailUsername': user, 'Password' : passwd, 'fpLogin' : 'Log In'} )
    data = data.encode('utf-8')

    try:
        result = opener.open("https://secure.bebo.com/SignIn.jsp", data)
    except urllib.error.HTTPError:
        return (2, None)

    if result.geturl() == "https://secure.bebo.com/JSRedirect.jsp?Location=SignIn.jsp":
        return (3, None)
    else:
        return (0, opener)

def get_photo_link(opener):
    """ Parse the link to the photo album page from bebo home page """
    # Could have just parsed the memberid number,
    # but if bebo change's it's link format, hopefully this way will still work
    
    res = opener.open("https://secure.bebo.com")
    soup = BeautifulSoup(res)

    site_menu_div = soup.find(id='site-menu')
    
    # Hopefully searching like this will be fairly resilient to changes in the page layout
    def check_span(tag):
        return tag.name == 'a' and tag.find('span', text='Photos', recursive=False) != None

    photo_link = site_menu_div.find(check_span)
    
    return photo_link['href']


def get_albums(opener, photo_link):
    """ Gets each album's name and url and returns them in a list of tuples """
    
    soup = BeautifulSoup(opener.open(photo_link))
    paginator = soup.find(id='paginator')
    
    other_pages = [ li.find('a')['href'] for li in paginator.find_all('li', class_=False) ]
    
    album_info = []
    album_info.extend(parse_album_page(soup))
    
    for page in other_pages:
        if "bebo.com" not in page:
            page = "http://www.bebo.com" + page

    soup = BeautifulSoup(opener.open(page))
    album_info.extend(parse_album_page(soup))

    return album_info


def parse_album_page(soup):
    """ Parses the album page and returns list of names and urls """

    ret_list = [] 
    album_list = soup.find(class_='grid albums-grid')
    
    for li in album_list.find_all('li'):
        album_link = li.find(class_='thumb-label').find('a')
        album_href = album_link['href']
        
        if "bebo.com" not in album_href:
            album_href = "http://www.bebo.com" + album_href

        ret_list.append( (album_link['title'], album_href) )

    return ret_list


def download_album(name, link, outdir, opener):
    """ Downloads album pics to folder in outdir """
    # This function is probably the most sensitive to bebo changing it's format 
    
    print('Downloading: "', name, '"', end='', sep='')

    for i in range(5):
        try:
            soup = BeautifulSoup(opener.open(link))
        except (urllib.error.HTTPError, urllib.error.URLError):
            time.sleep(0.3 * i)
            if i == 4:
                raise
        else:
            break

    #The album info is returned in a json format
    dyn_vals_json = soup.find('script', text=re.compile('DynamicValues '))     
    dyn_vals_json = dyn_vals_json.text.replace("DynamicValues = ", '{ "DynamicValues" : ')
    dyn_vals_json = re.sub(";\s*$", "}", dyn_vals_json)
    
    dyn_vals = json.loads(dyn_vals_json)
    
    outdir = create_uniq_folder(os.path.join(outdir, name))

    try:
        photo_list = dyn_vals['DynamicValues']['Photos']['PhotoList']
    except KeyError:
        print()
        return

    total_error = 0

    for index, photo in enumerate(photo_list):
            
        file_url = photo['large_file_name']     # There is an original filename too, but sadly it 404s
        
        date = photo['create_dttm']
        caption = photo['caption_tx']
        ext = os.path.splitext(file_url)[1]
        
        if caption.strip() == "":
            caption = "IMAGE"

        if file_url.startswith("file"):
            file_url = re.sub("^file", "http://i4.bebo.com/", file_url)
        elif file_url.startswith("bb"):
            file_url = re.sub("^bb", "http://bb.bebo.com/bb", file_url)

        filename = re.sub("\.[a-zA-Z]{3,4}", '', caption) + " (" + os.path.splitext(date)[0] + ")" + ext
        filename = get_uniq_valid_filename(outdir, filename)
        
        for i in range(5):
            try:
                urllib.request.urlretrieve(file_url, filename)
            except (urllib.error.HTTPError, urllib.error.URLError):
                time.sleep(0.3 * i)
                if i == 4:
                    print("\nError downloading file:", file_url, '\n')
                    total_error = total_error + 1
                    if total_error > 5:
                        raise

            except ValueError:
                total_error = total_error + 1
                print("\nError downloading file:", file_url, '\n')
                if total_error > 5:
                    raise
                break
                
            else:
                break
    
        print('\rDownloading: "', name, '"\t(', index + 1, '/', len(photo_list), ')          ', end='', sep='')

    print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bebo Photo Downloader')
    parser.add_argument('-u', dest='username', help='Bebo Username')
    parser.add_argument('-o', dest='outdir', metavar='DIR',  help='Download Directory for Albums', default=os.getcwd())
    
    args = parser.parse_args()
    (username, password) = get_user_pass(args.username)
    
    (err, opener) = bebo_login(username, password)
    
    if err == 3:
        sys.exit("Incorrect username or password.")
    elif err != 0:
        sys.exit("Unable to connect to bebo.")
    else:
        print("Login Successful.")
    
    outdir = create_uniq_folder(os.path.join(args.outdir, username))

    try:
        photo_link = get_photo_link(opener)
        album_info = get_albums(opener, photo_link)
    except (urllib.error.HTTPError, urllib.error.URLError):
        sys.exit("ERROR: Unable to load album info")
    except AttributeError:
        sys.exit("ERROR: Unable to parse album info.")
    
    for album in album_info:
        try:
            download_album(album[0], album[1], outdir, opener)
        except (KeyError, ValueError, AttributeError, urllib.error.HTTPError, urllib.error.URLError):
            print('Error loading album "', album[0], '".', sep='')
            raise
        else:
            print('Album "', album[0], '" downloaded successfully.', sep='')
    
    print("Done")

