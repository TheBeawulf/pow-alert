#! /usr/bin/env python

import sys
from skimage import io
import requests
import re
import json
from bs4 import BeautifulSoup
import notifications
import parse_img
from resort_names import *
import SQLitedb as sql
import time

day = time.strftime("%d")
month = time.strftime("%m")
year = time.strftime("%Y")
date = f"{year}_{month}_{day}"

resort_names = [CYPRESS, WHISTLER]
PLOT_DEBUG = False

class Resort:

    def __init__(self, name, cam_url=None, info_url=None):
        self.name = name or "default"
        self.webcam_url = cam_url
        self.info_url = info_url
        self.webcam_img = None
        self._24hsnow = ""
        self._12hsnow = ""
        self.extra_info = ""

    def update(self):
        if self.webcam_url:
            self.webcam_img = io.imread(self.webcam_url)
            self._12hsnow = parse_img.read_height(image=self.webcam_img,
                                                  debug_option=PLOT_DEBUG,
                                                  resort=self.name)
        page = requests.get(self.info_url)
        with open(f"log/HTML/{date}_{self.name.title()}.html", "w") as html_log_file:
            html_log_file.write(page.text)

        handler_fnc = getattr(self, f'update_{self.name}')
        return handler_fnc(page)

    def update_whistler(self, page):
        text_json = re.search('FR.snowReportData = ({.*});', page.text)
        data = json.loads(text_json.groups()[0])
        self._24hsnow = data['TwentyFourHourSnowfall']['Centimeters']
        self._12hsnow = data['OvernightSnowfall']['Centimeters']

    def update_cypress(self, page):
        soup = BeautifulSoup(page.content, 'html.parser')
        all_div = soup.find_all('div', class_='weather-item clearfix')
        for div in all_div:
            if "24 hr Snow" in div.text:
                el = div.find('span', class_='numbers')
                self._24hsnow = el.text.split(' ')[0]
                break
        div = soup.find('div', class_='additional-info')
        if div.text != "":
            self.extra_info = div.text

    def update_seymour(self, page):
        soup = BeautifulSoup(page.content, 'html.parser')
        tds = soup.find_all('td')
        for td in tds:
            if "Last 24 hours" in td.text:
                fall = td.text.split(' ')[3]
                self._24hsnow = re.sub('[a-z]', '', fall)
                break

    def display_info(self):
        print(f"{self.name.tittle()} report:")
        print(f"{self._12hsnow} cm overnight")
        print(f"{self._24hsnow} cm last 24h")
        print(f"Special resort info: {self.extra_info} ")
        print("******************")

    @property
    def data(self):
        self.update()
        return {'name':self.name, '12':self._12hsnow, '24':self._24hsnow, 'info':self.extra_info}


resort_dict = {
    CYPRESS: Resort(name=CYPRESS,
                    cam_url="http://snowstakecam.cypressmountain.com/axis-cgi/jpg/image.cgi?resolution=1024x768",
                    info_url="http://www.cypressmountain.com/downhill-conditions/"),

    WHISTLER: Resort(name=WHISTLER,
                     info_url="https://www.whistlerblackcomb.com/the-mountain/mountain-conditions/snow-and-weather-report.aspx"),

    SEYMOUR: Resort(name=SEYMOUR,
                    info_url="http://mtseymour.ca/conditions-hours-operation")
}


def check_snow(resort_list_names=None):
    names = resort_list_names or resort_dict.keys()
    result = []
    for name in names:
        result.append(resort_dict[name].data)
    return result


def pretify_data(data):
    txt = "**Snow Report**"
    for resort in data:
        txt = f"{txt}\n{resort['name'].title()}:"

        if resort['12']:
            txt = f"{txt}\n{resort['12']}cm last 12h"
        if resort['24']:
            txt = f"{txt}\n{resort['24']}cm last 24h"
        if resort['info']:
            txt = f"{txt}\nSPECIAL NOTICE: {resort['info']}"

    txt = f"{txt}\n******************"
    return txt


if __name__ == "__main__":
    try:
        PLOT_DEBUG = sys.argv[1]
    except IndexError:
        PLOT_DEBUG = False

    fresh_snow = False
    registered_numbers = sql.query_registered_numbers()

    txt= "**Snow Report**"
    for resort in resort_dict.values():
        txt = f"{txt}\n{resort.data['name'].title()}:"

        if resort.data['name'] == CYPRESS:
            if resort.data['12'] == "Trace":
                resort.data['12'] = 0;
            if resort.data['24'] == "Trace":
                resort.data['24'] = 0;

        if resort.data['12']:
            txt = f"{txt}\n{resort.data['12']}cm last 12h"
        if resort.data['24']:
            txt = f"{txt}\n{resort.data['24']}cm last 24h"
        if resort.data['info']:
            txt = f"{txt}\nSPECIAL NOTICE: {resort.data['info']}"

        txt = f"{txt}\n******************"

        if resort.webcam_img is not None:
            io.imsave(f"log/CAM/{date}_{resort.name.title()}_cam.png", resort.webcam_img)

        if resort._12hsnow and int(resort._12hsnow) > 0: # Mt Seymour doesnt have a 12h snow report
            fresh_snow = True

    if fresh_snow:
        for number in registered_numbers:
            notifications.send_sms(txt, number)


