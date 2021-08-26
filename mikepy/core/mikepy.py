# -*- coding: utf-8 -*-
#
# @Author: CPS
# @email: 373704015@qq.com
# @Date: 2021-07-19 09:16:56.383902
# @Last Modified by: CPS
# @Last Modified time: 2021-07-19 09:16:56.383902
# @file_path "Z:\CPS\MyProject\mikepy\core"
# @Filename "mikepy.py"
# @Description: 功能描述
#

import time, os
import pandas as pd
import geopandas as gpd

import numpy as np
# import matplotlib.pyplot as plt

from mikeio import Dfsu,Mesh
# from mikeio.spatial import Grid2D

from hashlib import md5
from tempfile import TemporaryDirectory
from shutil import copy2

# 插值库
from scipy.interpolate import griddata
from pykrige import OrdinaryKriging

if str(pd.__version__) != '1.3.0':
    print("本插件仅支持 pandas 1.3.0 (否则失去保存xls功能)")
    # exit()

class MikeIo(object):
    def __init__(self):
        self.dfs=None
        self.mesh=None
        self.len=0
        self.currt_file=""

        self.x = []
        self.y = []

        self.data={} # {'sheet_name':[{'column_name':'xxxxx', 'column_data':'xxxxx', 'file_name':'xxxxx'}]}
        self.file_list = []
        self.tmp_dir = None

    def __len__(self):
        return len(self.file_list)

    def __str__(self):
        return f"当前已处理 {len(self.file_list)} 个文件： {[*self.file_list]}"


    def read(self, filename:str, item:str="", column_name:str="", setp=-1, sheet_name:str="", method='cubic')->dict:
        """
        Description 获取指定类型、时间步长的对应数据

        - param self        :{params} {description}
        - param filename    :{str}    文件名，绝对路径
        - param item        :{str}    需要提取的数据类型|Current_direction|Current_speed|U_velocity|V_velocity|...
        - param column_name :{str}    属性最终的列名
        - param setp        :{int}    需要获取的步长，默认是最后一个时间
        - param sheet_name  :{str}    数据的sheet_name，指定后

        returns `{dict}` {description}
        ```py
        {
            sheet_name1:[{
                "column_name":column_name,
                "file_name":name,
                "column_data":np.round(data, 3),
            }],
            sheet_name2:[{../},{../}]
        }
        ```
        """
        data = []
        name,ext = os.path.basename(filename).split('.')
        if ext == 'dfsu':
            # 防止重复读取同一文件
            if self.currt_file != filename:
                try:
                    self.dfsu = Dfsu(filename)
                    self.currt_file = filename
                except Exception:
                    print('tips >>> 使用英文或数字命名文件，数据提取速度将会大大提升')
                    tmp_file = self.create_tmp_file(filename)
                    self.dfsu = Dfsu(tmp_file)
                    self.currt_file = filename

            if not self.dfsu: return print(f'无法读取文件{filename}')

            # 通过self.dfsu 读取数据
            data = self.get_dfsu_data(item=item, setp=setp)

        if len(data) == 0 :
            print('data 异常')
            return self

        if len(self.x) == 0 or len(self.y) == 0:
            print('当前还没定义需要输出的xy，此处定义')
            # 当前还没定义需要输出的xy，此处定义
            self.set_xy_by_mesh()


        # 判断是否需要插值
        if len(self.x) != len(data):
            # 根据xy来重新插值数据
            print("根据xy来重新插值数据: ")
            points = self.dfsu.element_coordinates[:,0:2]
            data = self.get_data_by_xy(self.x, self.y, points, data, method)
            data = self.check_data(data)

        if sheet_name == "": sheet_name = f'mesh_{len(data)}'
        if column_name == "": column_name = name
        if not sheet_name in self.data: self.data[sheet_name] = []

        self.data[sheet_name].append({
            "column_name":column_name,
            "file_name":name,
            "column_data":np.round(data, 3),
        })

        # 记录已处理过的文件
        if not f'{name}.{ext}' in self.file_list:
            self.file_list.append(f'{name}.{ext}')

        return data

    @staticmethod
    def get_data_by_xy(x, y, points, data, method='cubic'):

        interpolate_res = []
        if method == 'Kriging':
            # 定义数据
            Kriging = OrdinaryKriging(points[0], points[1], data, variogram_model='gaussian', nlags=6)
            interpolate_res, ss = Kriging.execute('grid', x, y)
            # xgrid,ygrid = np.meshgrid(x, y)

        else:
            # 根据 x，y 生成一个矩阵容器
            xi,yi = np.meshgrid(x, y)

            # cubic 插值
            interpolate_res = griddata(points, data, (xi,yi), method=method)

        # 获取对角线索引
        index = list(range(len(x)))

        # 获取对角线数据
        res = pd.DataFrame(interpolate_res).values[index,index]

        return  res

    # 读取dfsu文件
    def get_dfsu_data(self, item:str, setp:int=-1):
        # 防重读取
        res = None

        if item.lower() =="current direction":
            res = self.get_dfsu_direction(setp)[:]

        elif item.lower() =="current speed":
            res = self.get_dfsu_speed(setp)[:]

        else:
            res = self.dfsu.read([item])[0][setp][:]

        return self.check_data(res)


    # 获取dfsu文件的流速数据
    # return {narray}
    def get_dfsu_direction(self, setp:int=-1):
        try:
            u,v = self.dfsu.read(['U velocity','V velocity'])
            u = u[setp]
            v = v[setp]
            return np.mod(90 -np.rad2deg(np.arctan2(v,u)), 360)
        except KeyError:
            return self.dfsu.read(['Current direction'])[0] * 180/3.14

    # 获取dfsu文件的流速数据
    # return {narray}
    def get_dfsu_speed(self, setp:int=-1):
        try:
            u,v = self.dfsu.read(['U velocity','V velocity'])
            u = u[setp]
            v = v[setp]
            return np.sqrt(u**2 + v**2)
        except KeyError:
            return self.dfsu.read(['Current speed'])[0]


    def check_data(self, data, fix=True, tip=True):
        """
        Description {description}

        - param self :{params} {description}
        - param data :{params} {description}
        - param fix  :{bool}   是否修复为0
        - param tip  :{bool}   是否打印出提示信息

        returns `{}` {description}

        """
        name, ext = os.path.basename(self.currt_file).split('.')
        for index, each in enumerate(data):
            if not np.isnan(each): continue

            if fix : data[index] = 0

            # if tip : print(f"warning >>> file：{name}.{ext}，posistion：<{ index + 1 }> has unknown value")
            if tip : print(f"警告！ >>> 文件：{name}.{ext}，位置：<{ index + 1 }> 的数据为空值")

        return data


    def create_tmp_file(self, filename):
        # 创建临时目录
        if not self.tmp_dir: self.tmp_dir = TemporaryDirectory()

        # 记录当前文件已经被缓存
        name,ext = os.path.basename(filename).split('.')

        # 已 md5 命名临时文件
        md5_name = md5(name.encode('utf8')).hexdigest()
        tmp_file = f'{self.tmp_dir.name}{os.path.sep}{md5_name}.{ext}'

        # 复制文件到临时目录，同时先检查是否已存在临时文件
        if not os.path.exists(tmp_file):
            copy2(filename, tmp_file)

        return tmp_file

    def set_xy(self, tar, sep:str=r"\s+"):
        x = y = []

        if isinstance(tar, str):
            if tar.endswith('.xyz'):
                xyz = pd.read_table(tar, header=None, sep=sep)
                x = xyz[0]
                y = xyz[1]

        if len(x)>0 and len(y)>0:
            # self.data['x'].append({'column_name':'x','column_data': x})# x 为第一列数据
            # self.data['y'].append({'column_name':'y','column_data': y})# y 为第二项数据
            self.x = x
            self.y = y
        else:
            raise "xy读取错误"

        return self

    def set_xy_by_mesh(self, dfs):
        # 实例化网格
        # 获取网格内的数据[col1, col2, col3,...]
        if not dfs:
            self.mesh = Mesh(self.currt_file)
            xyz = self.mesh.element_coordinates
        else:
            xyz = dfs.element_coordinates

        # 以网格数量为基础创建一个对象，收集同一网格的所有数据
        # sheet_name = f'mesh_{len(xyz)}'
        data = pd.DataFrame(xyz)
        # self.data['x'].append({'column_name':'x','column_data': data[0]})# x 为第一列数据
        # self.data['y'].append({'column_name':'y','column_data': data[1]})# y 为第二项数据
        self.x = data[0]
        self.y = data[1]


        return data



    # 根据后缀名，导出excel文件，支持 shp/excel/xyz
    def save(self, filename='./output.xls'):
        # 格式化输出名，添加时间
        name,ext = os.path.basename(filename).split('.')
        d = os.path.dirname(filename)
        output = f'{d}{os.path.sep}{name}_{int(time.time())}.{ext}'

        if ext == 'xls' or ext == "xlsx":
            self.to_excel(self.data, output)
        elif ext == 'shp':
            self.to_shp(self.data, output)

        return self

    def clean(self):
        if self.tmp_dir:self.tmp_dir.cleanup()
        print('^.^ done！')

    def to_excel(self, data, filename):
        print("self.y: ", len(self.y))
        print("self.x: ", len(self.x))

        writer = pd.ExcelWriter(filename)
        for sheet_name, values in data.items():
            print("sheet_name: ", sheet_name)
            # print("data[sheet_name]: ", data[sheet_name])

            data[sheet_name].insert(0, {'column_name':'y','column_data': self.y})
            data[sheet_name].insert(0, {'column_name':'x','column_data': self.x})

            # 生成数据对象
            sheet_data = { each_column['column_name']:each_column['column_data'] for each_column in values if each_column}

            # 根据数据的key 保证相同网格数据保存在同一sheet_name
            pd.DataFrame(sheet_data).to_excel(writer, index=False, sheet_name=sheet_name)

        writer.save()

    def to_shp(self, dataframe, filename):
        # dataframe = pd.DataFrame({'sp': data})

        shp = self.dfsu.to_shapely()
        poly_list = [e for e in shp]

        gdf = gpd.GeoDataFrame(dataframe, geometry=poly_list)
        gdf.to_file(filename)

    # target1 - target2 计算差值
    def sub(self, target1:str, target2:str, sheet_name:str, column_name:str=""):
        """
        Description  计算两个数据的差值，流速差值、水位差值等计算

        - param self    :{params} {description}1
        - param target1 :{params} {description}
        - param target2 :{params} {description}
        - param title   :{string} {description}

        returns `{}` {description}

        """
        tar1 = tar2 = []
        for each_column in self.data[sheet_name]:
            print('当前 name', each_column["column_name"])
            print('当前 target1', target1)
            print('当前 target2', target2)

            if len(tar1) == 0 and each_column["column_name"] == target1:
                tar1 = each_column["column_data"]
                continue

            if len(tar2) == 0 and each_column["column_name"] == target2:
                tar2 = each_column["column_data"]
                continue

        if len(tar1) == 0: return print('没有找到target1 数据')
        if len(tar2) == 0: return print('没有找到target2 数据')

        sub = np.round(tar1 - tar2, 3)
        sub = self.check_data(sub)

        if column_name == "":
            column_name = f'{target1}_{target2}'

        self.data[sheet_name].append({ "column_data":sub,"column_name":column_name })

        return sub



if ( __name__ == "__main__"):
    tar1 = '../data/BE-20.dfsu'
    tar2 = '../data/sg-north-20.dfsu'
    xyz1 = r'../data/BE-20.xyz'
    xyz2 = r'../data/sg-north-20.xyz'

    M = MikeIo()

    M.set_xy(xyz1)
    # M.read(tar1)

    print(type(M.x))
    print(type(M.y))

    # M.read(tar1, item="Current speed", column_name='BE20_cubic', sheet_name='s1', method='cubic')
    # M.read(tar1, item="Current speed", column_name='BE20_linear', sheet_name='s1', method='linear')
    # M.read(tar1, item="Current speed", column_name='BE20_nearest', sheet_name='s1', method='nearest')

    # M.save('../data/test.xlsx')

