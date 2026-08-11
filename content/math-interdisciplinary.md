先说结论，纯数基本上是死路，而盲目转码也不见得有优势，交叉方向包括AI4Science比较容易搞出点东西来。但是能做出来任何和数学相关的内容几乎不可能，除非遇到老师给你喂饭。

以下内容基本根据个人理解来进行阐述，与其说是建议，更像是同为数学系学生的经验分享，参考价值不大，如果能抛砖引玉当然更好。

看了上一条提问题主应该不是那种想要一门心思学数学的，既然如此，那就排除掉了所有的纯数方向，因此哪怕做交叉也无需考虑那种过于理论的。这与天赋和高校层次无关，昔烟大张若冰的起点更低，但他们无不是抱有十年饮冰难凉热血的，当然，答主也做不到。根据所在学院的某位老师上课曾经说过，“不是所有的人都能学数学，哪怕已经是985的数院学生”。

接着，我们就得到了一些可能的方向，包括[计算数学](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=计算数学&zhida_source=entity)，[运筹学](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=运筹学&zhida_source=entity)，[金融数学](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=金融数学&zhida_source=entity)等。当然，最重要的大概就是加入伟大的深度学习，做AI4Math。不但数院确实有老师在做比较方便，而且和cs等新工科也算得上无缝衔接。

在此基础上，我会基于一下我目前折腾了一年半载几乎没什么产出的结果，回答一些你可能会问的问题。

### 为什么要选AI4math方向

主要是从众效应，几年前图像处理火大家就去做[压缩感知](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=压缩感知&zhida_source=entity)，做小波理论，现在AI火了自然也就去做AI；其次就是确实有需要，数学在AI领域不能说是毫无必要吧，至少也可以说是无处不在了：不但一些底层逻辑例如[优化器](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=优化器&zhida_source=entity)，[损失函数](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=损失函数&zhida_source=entity)与[线性代数](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=线性代数&zhida_source=entity)，优化，[概率论](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=概率论&zhida_source=entity)等课程强相关，数学发挥直接价值；而且数学的很多理论例如统计，[PDE](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=PDE&zhida_source=entity)，[随机分析](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=随机分析&zhida_source=entity)也能很好的适用于描述深度学习，它们实现了不仅仅是炫技，更多是揭示了AI的性质。

### 选择具体的AI交叉方向

要么就是用AI去做一些数学的工作，一大重点就是求解方程，用AI的方法，例如[神经网络](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=神经网络&zhida_source=entity)来求解[偏微分方程](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=偏微分方程&zhida_source=entity)（PINNs），当然这些方程往往还会结合具体的情景，要想发出论文来还得选一些不好解的方程，奇异的方程之类的。

其次就是用数学的一些理论，主要是统计学，概率论，PDE,动力系统去分析AI，例如机器学习，深度学习，强化学习。但这东西实际上也没个说法，也可以更简单一点，去改一下网络的结构，主要是优化和线性代数的部分，去更好的求解这个问题。

如果还打算去学生物的话也可以去做[生物信息学](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=生物信息学&zhida_source=entity)，不过这和代码的要求更高。

要具体选择哪些方向完全说不好，上面说的两个东西其实也没什么分别。而具体的选择还得去问老师。数院的老师不一定懂AI，但是正如那句老话，机器学习的前提是自己学明白。大部分做计算，优化，统计的老师基本上都会做一点AI。如果你打算去做AI4Math但是又没啥大致思路

### 不算规划的规划和你可能会遇到的困难

未来可能在ICM畅谈AI4Math的人现在还很年轻，不同于代数几何或者数论的同学有基本明确的教材序列，而且我也不知道该做什么，只知道要读研，只说点绕的弯路吧。

首先多学点数学肯定没错，重点是数分高代概率统计，这些工科会的你肯定得会，你还要学的更深，搞明白他们搞不明白的测度空间，可积性证明。其次就是应用相关的课程，[数值线性代数](https://zhida.zhihu.com/search?content_id=759250987&content_type=Answer&match_order=1&q=数值线性代数&zhida_source=entity)（求解线性方程组），优化（求解非线性函数的极小值）。至于其它的学不学？抽代，拓扑，复变，随机过程，泛函分析……菜名就不报了，数院的学生把主要精力花在数学上在正常不过了。

其次就是代码。首先明确一点就是不要畏难，你不需要去和算法竞赛ACM校队比这个。与其焦虑自己为啥还是不会横向比较同龄人数学和代码完全cover你的水平。关心自己能增长多少就增长多少的增量问题，花一个月在搜索栏里面搜索python,把pycharm,anaconda都装在电脑里面根本就不是个事。

先把hello world敲明白，条件循环写清楚。学会了基本的语法之后，搜索github,注册一个账号，你会在上面找到你所需要的，关于深度学习数据处理的工具numpy，pytorch的使用工具，学会把这些平台加载到你的电脑里，建一个仓库把你写的破铜烂铁给丢上去。

然后就是上点计算机相关的课程，主要就是数据结构与算法，数据库，前者告诉你数据是怎么分布在电脑里的，以及一些基本的排序，查找算法。并且通过这些课程判断自己到底是留在数院更多做理论还是干脆直接转码。

此外，就是全面的学好计算数学。如何算一个线性方程组？如何取到一个函数的最小值？如何求解一个微分方程？你会学习很多计算的方法，并且知道很多东西算不出来，只能算出一个数。那么，如何把那个数给算出来就是你需要会的。有一个数值计算工具：Matlab,专为数值计算设计，把那些例子算明白就是你需要做的，哦对了，github上应该也是有的。

最后，你如果选择了AI交叉的方向，现在以及将来会在这个过程遇到很多的困难。

包括单纯的学业上的苦难，但不限于写不明白数学证明，看不明白算法，下不明白pycharm,下不明白anaconda,连不上github，搜不到任何的可供参考的内容，写不明白算法，不知道为什么自己既写不来算法也写不来证明，或者资源上的困难，缺乏可以讨论的伙伴，缺乏可以提供全贯通式培养的路径，缺乏指导。

唯一能给的经验就是，捷径是最长的路。短期内做任何事都做不出来，包括论文，包括数学，包括代码，本科生科研全都是小孩子过家家，经历和过程比结果更重要。不过这种结果也是从过家家中过出来的。
