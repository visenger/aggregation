import numpy as np
import cv2
import os
from subprocess import call
__author__ = 'ggdhines'

spacing = 35

class TesseractUpdate:
    def __init__(self):
        self.boxes = {}
        self.row_pointer = None
        self.column_pointer = None
        self.training_page = None

        self.box_file = []

        if not os.path.exists("/tmp/tessdata"):
            os.makedirs("/tmp/tessdata")

        with open("/tmp/tessdata/active_weather.lobster.exp0.box","w") as f:
            f.write("")

    def __create_blank_page__(self):
        """
        create a blank page where we'll put labelled characters
        :return:
        """
        self.width = 2508
        self.height = 2480
        self.training_page = np.zeros((self.height,self.width),dtype=np.uint8)
        self.training_page.fill(255)

        self.row_bitmaps = []
        self.row_characters = []

        self.row_pointer = spacing
        self.column_pointer = spacing

        self.used_height = spacing

    def __flush_row__(self):
        """
        add each of the saved characters into the row
        :return:
        """
        if self.row_bitmaps != []:

            self.__training_image_output__()
            self.__box_file_output__()

            # move onto the next row
            row_height = max([b.shape[0] for b in self.row_bitmaps])

            self.row_bitmaps = []
            self.row_characters = []
            self.column_pointer = spacing
            self.row_pointer += spacing + row_height

    def __get_image_height__(self):
        """
        we'll trim the training image to be not much bigger than the text so return the height
        :return:
        """
        if self.row_bitmaps == []:
            return self.row_pointer+spacing
        else:
            row_height = max([b.shape[0] for b in self.row_bitmaps])
            return self.row_pointer+row_height+spacing

    def __training_image_output__(self):
        """
        put the bitmaps into the training image
        :return:
        """
        column_pointer = spacing

        for b in self.row_bitmaps:
            assert isinstance(b,np.ndarray)
            height,width = b.shape

            # row first and then column
            self.training_page[self.row_pointer:self.row_pointer+height,column_pointer:column_pointer+width] = b

            column_pointer += width + spacing
        print([b.shape for b in self.row_bitmaps])

        # cv2.imwrite("/tmp/tessdata/active_weather.lobster.exp0.tiff",self.training_page[:self.__get_image_height__(),:])
        cv2.imwrite("/tmp/tessdata/active_weather.lobster.exp0.tiff",self.training_page)

    def __box_file_flush__(self):
        pruned_height = self.__get_image_height__()
        with open("/tmp/tessdata/active_weather.lobster.exp0.box","w") as f:
            for a,b,c,d,e in self.box_file:
                f.write(str(a)+" "+str(b)+" "+str(c)+" " + str(d) + " " + str(e) + " 0\n")


    def __box_file_output__(self):
        """
        write out the current line of characters to the box files
        :return:
        """
        column_pointer = spacing
        # pruned_height = self.__get_image_height__()

        # with open("/tmp/tessdata/active_weather.lobster.exp0.box","a") as f:
        for char,b in zip(self.row_characters,self.row_bitmaps):
            # calculate the coordinates for the box file
            height,width = b.shape

            # save the values to list since we will be adjusting the image size based on how much
            # we actually write to to the image
            # print(self.height,self.row_pointer)
            self.box_file.append([char,column_pointer,self.height-(self.row_pointer+height-1),column_pointer+width-1,self.height-self.row_pointer])

            # # start with the character label
            # f.write(char + " ")
            # # and the column (x-axis) lower bound
            # f.write(str(column_pointer) + " ")
            # # and the row (y-axis) lower bound
            # f.write(str(pruned_height-(self.row_pointer+height)+1) + " ")
            # # and then the column upper bound
            # f.write(str(column_pointer+width-1) + " ")
            # # and then finally the row upper bound - and add in the page number too
            # f.write(str(pruned_height-self.row_pointer) + " 0\n")
            # # f.write(str(self.max_height-b+spacing) + " " + str(c) + " " + str(self.max_height-d+spacing) + " 0\n")
            #
            column_pointer += width + spacing

    def __add_char__(self,character,bitmap):
        """
        add a new character to our 'training page'
        and flush out the row if we gone too far
        :param character:
        :param additional_y_offset:
        :return:
        """
        char_height,char_width = bitmap.shape

        # do we have too many characters for this row?
        # if so - flush
        if (self.column_pointer+char_width) >= self.width-spacing:
            self.__flush_row__()

        self.row_bitmaps.append(bitmap)
        self.row_characters.append(character)
        self.column_pointer += char_width + spacing


    # def __add_characters__(self,char_list,image_list,minimum_y):
    #     """
    #     add a whole bunch of characters all at once - while keeping track of what the characters are
    #     so we can add them to the box file
    #     :param char_list:
    #     :param image_list:
    #     :param minimum_y:
    #     :return:
    #     """
    #     top_of_row = min(minimum_y)
    #
    #     for char,img,my in zip(char_list,image_list,minimum_y):
    #         additional_y_offset = my-top_of_row
    #
    #         a,b,c,d = self.__add_char__(img,additional_y_offset)
    #         self.boxes[(a,b,c,d)] = char
    #
    #         self.max_height = max(self.max_height,b)
    #         self.max_width = max(self.max_width,c)
    #
    #     cv2.imwrite("/home/ggdhines/test.jpg",self.training_page)

    # def __write_training__(self):
    #     """
    #     write out the 'training page' and the box file
    #     :return:
    #     """
    #     if not os.path.exists("/tmp/tessdata"):
    #         os.makedirs("/tmp/tessdata")
    #
    #     to_save = self.training_page[0:self.max_height+spacing,0:self.max_width+spacing]
    #
    #     cv2.imwrite("/tmp/tessdata/active_weather.lobster.exp0.tiff",to_save)
    #
    #     with open("/tmp/tessdata/active_weather.lobster.exp0.box","wb") as f:
    #         for (a,b,c,d),char in self.boxes.items():
    #             f.write(char + " " +str(a) + " ")
    #             f.write(str(self.max_height-b+spacing) + " " + str(c) + " " + str(self.max_height-d+spacing) + " 0\n")

    def __update_tesseract__(self):
        """
        actually run the code to update Tesseract
        :return:
        """
        self.__flush_row__()

        self.__box_file_flush__()

        os.chdir('/tmp/tessdata')
        call(["tesseract", "active_weather.lobster.exp0.tiff", "active_weather.lobster.exp0", "nobatch" ,"box.train"])
        # call(["unicharset_extractor", "active_weather.lobster.exp0.box"])
        call(["unicharset_extractor", "*.box"])

        with open("/tmp/tessdata/font_properties","w") as f:
            f.write("lobster 0 0 0 0 0\n")

        os.system("shapeclustering -F font_properties -U unicharset active_weather.lobster.exp0.tr")
        # "mftraining -F font_properties -U unicharset -O active_weather.unicharset active_weather.lobster.exp0.tr"
        os.system("mftraining -F font_properties -U unicharset -O active_weather.unicharset active_weather.lobster.exp0.tr")
        os.system("cntraining active_weather.lobster.exp0.tr")

        os.system("mv inttemp active_weather.inttemp")
        os.system("mv normproto active_weather.normproto")
        os.system("mv pffmtable active_weather.pffmtable")
        os.system("mv shapetable active_weather.shapetable")
        os.system("combine_tessdata active_weather.")