## Dependencies
import gzip
import sys
import pandas as pd
import numpy as np
import plotly, plotly.express as px


## Windowed pca scripts

def parse_arguments():
    '''
    Parse command line arguments & print help message if # of arguments is incorrect
    '''

    global variant_file_path, metadata_path, output_prefix, chrom, start, stop, w_size, w_step, \
        pc, taxon, group, color_taxon, guide_samples

    # fetch arguments    
    _, variant_file_path, metadata_path, output_prefix, region, w_size, w_step, pc, taxon, group, \
        color_taxon, guide_samples = sys.argv

    # print help message if incorrect number of arguments was specified
    if len(sys.argv) != 13:
        print('   python windowed_pca.py <variant file> <metadata> <output prefix> <region>\n\
                                <window size> <window step size> <filter column name>\n\
                                <filter column value> <color column name>\n\
                                <guide samples>\n\n\
            <variant file>         str  path to uncompressed or gzipped variant file\n\
                                        (VCF or genotype file; details -> README)\n\
            <metadata>             str  path to the metadata file (details -> README)\n\
            <output prefix>        str  prefix for output files\n\
            <region>               int  target region in format "chr:start-stop"\n\
                                        (i.e. chr1:1-chrom_length to analyze the\n\
                                        entire chr1)\n\
            <window size>          int  sliding window size in bp, e.g. "1000000"\n\
            <window step>          int  sliding window step size in bp, e.g. "10000"\n\
            <pc>                   int  principal component to use ("1" or "2")\n\
            <filter column name>   str  metadata column name to filter for\n\
                                        individuals to includede in the analysis,\n\
                                        e.g. "genus" (see <filter column value>)\n\
            <filter column value>  str  value to be filtered for in filter column;\n\
                                        Setting <filter column name> to "genus" and\n\
                                        <filter column value> to "Homo" would\n\
                                        include all individuals of the genus Homo\n\
                                        in the output, while ignoring all others.\n\
                                        (a comma-separated list of include values\n\
                                        can be provided, e.g. "Homo,Pan")\n\
            <color column name>    str  metadata column to assign colors by in the\n\
                                        output plot; if selecting "genus", all\n\
                                        individuals from the same genus will have\n\
                                        the same color in the output plots; if\n\
                                        specifying a comma-separated list like \n\
                                        "genus,species", one output plot is \n\
                                        generated for each color scheme\n\
            <guide samples>        str  [optional] list of samples to use for\n\
                                        polarization, e.g. "ind1,ind2,ind3"\n\
                                        (details --> README)', file=sys.stderr)

    # fetch chrom, start, stop from regions string
    chrom = region.split(':')[0]
    start = region.split(':')[1].split('-')[0]
    stop = region.split(':')[1].split('-')[1]

    # change str to int where appropriate
    start, stop, w_size, w_step = int(start), int(stop), int(w_size), int(w_step)
    
    # change output_prefix to lower case
    output_prefix = output_prefix.lower()


def read_metadata(variant_file_path, metadata_path, taxon=None, group=None):
    '''
    Read in metadata, optionally filter by taxon ?and sort by gt_file sample order?
    '''

    # fetch sample names from genotype file header
    read_func = gzip.open if variant_file_path.endswith('.gz') else open
    with read_func(variant_file_path, 'rt') as gt_file:
        samples_lst = gt_file.readline().strip().split('\t')[2:]

    # read in metadata
    metadata_df = pd.read_csv(
        metadata_path,
        sep='\t',
    )

    # re-name first column to 'id' (this is the only required column and must have unique ids)
    metadata_df.columns.values[0] = 'id'

    # subset input samples to match taxon group specification if specified
    if taxon and group:
        metadata_df = metadata_df.loc[metadata_df[taxon].isin(group.split(','))]
    
    # remove individuals that are not in the genotype file
    exclude_lst = [x for x in list(metadata_df['id']) if x not in samples_lst]
    for i in exclude_lst:
        metadata_df.drop(metadata_df[metadata_df['id'] == i].index, inplace=True)
    
    # # get index of samples kept after filtering
    # sample_idx_lst = sorted([samples_lst.index(x) for x in list(metadata_df['id'])])
    # keep_id_lst = [samples_lst[x] for x in sample_idx_lst]

    # # sort metadata by VCF sample order 
    # metadata_df['id'] = pd.Categorical(metadata_df['id'], categories = keep_id_lst, ordered = True)
    # metadata_df.sort_values('id', inplace=True)

    return metadata_df


def polarize(w_pca_df, var_threshold, mean_threshold, guide_samples): ## IMPROVE GUIDESAMPLE SETTINGS
    '''
    Polarize windowed PCA output: if no guide_samples specified polarize PC orientation using a subset of samples 
    with large absolute values and small variability
    '''

    # if $guide_samples not manually specified, select the $var_threshold samples with the least variance, and 
    # from those the $mean_threshold with the highest absolute value accross all windows as guide samples to 
    # calibrate the orientation of all windows
    if guide_samples: # check if this makes sense from #############################################
        guide_samples = mean_threshold.split(',')
        guide_samples_df = w_pca_df.loc[guide_samples]
    else:
        guide_samples = list(w_pca_df.dropna(axis=1).abs().var(axis=1).sort_values(ascending=True).index[0:var_threshold])
        guide_samples_df = w_pca_df.loc[guide_samples]
        guide_samples = list(guide_samples_df.dropna(axis=1).abs().sum(axis=1).sort_values(ascending=False).index[0:mean_threshold])
    # to ###########################################################################################
    
    guide_samples_df = guide_samples_df.loc[guide_samples]

    # considering all guide samples, if the negative absolute value of each window is closer 
    # that in, switch orientation of that window
    # (1 --> switch, 0 --> keep)
    
    rows_lst = []    
    for row in guide_samples_df.iterrows():
        row = list(row[1])
        prev_window = row[0] if not row[0] == None else 0 # only if current window is None, prev_window can be None, in that case set it to 0 to enable below numerical comparisons
        out = [0]
    
        for window in row[1:]:

            if window == None:
                out.append(0)
                continue
            elif abs(window - prev_window) > abs(window - (prev_window*-1)):
                out.append(1)
                prev_window = (window*-1)
            else:
                out.append(-1)
                prev_window = window
    
        rows_lst.append(out)

    # sum up values from each row and save to switch_lst
    rows_arr = np.array(rows_lst, dtype=int).transpose()
    switch_lst = list(rows_arr.sum(axis=1))

    # switch individual windows according to switch_lst (switch if value is negative)
    for idx, val in zip(list(w_pca_df.columns), switch_lst):
        if val < 0:
            w_pca_df[idx] = w_pca_df[idx]*-1

    # switch Y axis if largest absolute value is negative
    if abs(w_pca_df.to_numpy(na_value=0).min()) > abs(w_pca_df.to_numpy(na_value=0).max()):
        w_pca_df = w_pca_df * -1

    return w_pca_df


def annotate(w_pca_df, metadata_df, pc):
    '''
    Pivot windowed pca output and annotate with metadata
    '''

    # annotate with metadata
    for column_name in metadata_df.columns:
        w_pca_df[column_name] = list(metadata_df[column_name])

    # replace numpy NaN with 'NA' for plotting (hover_data display)
    w_pca_df = w_pca_df.replace(np.nan, 'NA')

    # convert to long format for plotting
    w_pca_anno_df = pd.melt(w_pca_df, id_vars=metadata_df.columns, var_name='window_mid', value_name=pc)

    return w_pca_anno_df


def plot_w_pca(w_pca_df, pc, color_taxon, chrom, start, stop, w_size, w_step):
    '''
    Plot one PC for all included sampled along the chromosome
    '''

    fig = px.line(w_pca_df, x='window_mid', y='pc_' + str(pc), line_group='id', color=color_taxon, hover_name='id', 
                    hover_data=[x for x in list(w_pca_df.columns) if x not in ['window_mid', 'pc_' + str(pc)]],
                    width=(stop-start)/20000, height=500,
                    title=str('<b>Windowed PC ' + str(pc) + ' of ' + chrom + ':' + str(start) + '-' + str(stop) + '</b><br> (window size: ' + str(w_size) + ' bp, window step: ' + str(w_step) + ' bp)'), 
                    labels = dict(pc_1 = '<b>PC 1<b>', pc_2 = '<b>PC 2<b>', window_mid = '<b>Genomic position<b>'))

    fig.update_layout(template='simple_white', font_family='Arial', font_color='black',
                    xaxis=dict(ticks='outside', mirror=True, showline=True),
                    yaxis=dict(ticks='outside', mirror=True, showline=True),
                    legend={'traceorder':'normal'}, 
                    title={'xanchor': 'center', 'y': 0.9, 'x': 0.45})

    fig.update_xaxes(range=[start, stop])

    fig.update_traces(line=dict(width=0.5))

    return fig


def plot_w_stats(w_stats_df, chrom, start, stop, w_size, w_step, min_var_per_w):
    '''
    Plot per windowstats: % explained by PC1 and PC2 + # of variants per window
    '''
    global missing_stretches # delete
    # for simplicity
    go = plotly.graph_objects
    
    # initialize figure
    fig = plotly.subplots.make_subplots(
        specs=[[{'secondary_y': True}]],
        x_title='<b>Genomic position<b>',
        subplot_titles=[
            '<b>Per window stats of ' + chrom + ':' + str(start) + '-' + str(stop) + 
            '</b><br> (window size: ' + str(w_size) + ' bp, window step: ' + str(w_step) + ' bp)'
        ],
    )

    # pc_1 variance explained
    fig.add_trace(
        go.Scatter(
            x=w_stats_df.index,
            y=w_stats_df['pct_explained_pc_1'],
            name='PC 1',
            mode='lines',
            line=dict(color='#4d61b0', width=1),
            fill='tozeroy',
            connectgaps=True,
        ),
        secondary_y=False,
    )

    # pc_2 variance explained
    fig.add_trace(
        go.Scatter(
            x=w_stats_df.index,
            y=w_stats_df['pct_explained_pc_2'],
            name='PC 2',
            mode='lines',
            line=dict(color='#458255', width=1),
            fill='tozeroy',
            connectgaps=True,
        ),
        secondary_y=False
    )

    # plotly has a bug: if filling the area under the curve, the 'fill' doesn't break at missing 
    # data even when specifying connectgaps=True --> therefore, plot white rectangles on top to 
    # cover the missing data stretches
    missing_stretches, stretch = [], []
    pc_1_max = max(w_stats_df['pct_explained_pc_1'])
    for w_mid, n_variants in zip(w_stats_df.index, w_stats_df['n_variants']):
        if n_variants >= min_var_per_w:
            if stretch:
                missing_stretches.append(stretch)
                stretch = []
        else: stretch.append(w_mid)
    if stretch: missing_stretches.append(stretch)
    for stretch in missing_stretches:
        fig.add_trace(
            go.Scatter(
                x=[stretch[0], stretch[-1], stretch[-1], stretch[0]], 
                y=[0, 0, pc_1_max, pc_1_max], 
                fill='toself',
                mode='none',
                fillcolor='white',
                hoverinfo='skip',
                showlegend=False,
            )
        )
        
    # fill only regions between min_var_per_w and n_variants if n_variants < min_var_per_w this 
    # requires some hacks, such as adding a dummy datapoint at ± 0.0001 around missing stretches to 
    # delimit grey filled areas
    w_stats_gaps_df = w_stats_df.loc[w_stats_df['n_variants'] < min_var_per_w][['n_variants']]
    gap_edges = [x[0]-0.0001 for x in missing_stretches] + [x[-1]+0.0001 for x in missing_stretches]
    gap_edges_df = pd.DataFrame([min_var_per_w] * len(gap_edges), gap_edges, columns=['n_variants'])
    w_stats_gaps_df = pd.concat([w_stats_gaps_df, gap_edges_df]).sort_index()
    fig.add_trace(
        go.Scatter(
            x=w_stats_gaps_df.index,
            y=w_stats_gaps_df['n_variants'],
            mode='lines',
            line=dict(color='rgba(0, 0, 0, 0)'),
            hoverinfo='skip',
            showlegend=False,
        ),
        secondary_y=True,
    )

    # horizontal line to show min_var_per_w threshold
    fig.add_trace(
        go.Scatter(
            x=[start, stop],
            y=[min_var_per_w, min_var_per_w],
            mode='lines',
            line=dict(color='#595959', dash='dot', width=1),
            fill='tonexty',
            hoverinfo='skip',
            showlegend=False
        ),
        secondary_y=True,
    )

    # add annotation for min_var_per_w line
    fig.add_trace(go.Scatter(
        x=[stop],
        y=[min_var_per_w-0.05*min_var_per_w],
        mode='lines+text',
        text=['min # of variants threshold '],
        textposition='bottom left',
        textfont=dict(color=['#595959']),
        showlegend=False,
        ),
        secondary_y=True,
    )

    # number of variants per window
    fig.add_trace(
        go.Scatter(
            x=w_stats_df.index,
            y=w_stats_df['n_variants'],
            name='# variants',
            mode='lines',
            line=dict(color='#595959', dash='dot', width=1)
        ),
        secondary_y=True,
    )

    fig.add_hline(
        y=min_var_per_w,
        secondary_y=True,
    )

    # set x axis range
    fig.update_xaxes(
        range=[start, stop],
    )
    
    # set y axes ranges and titles
    fig.update_yaxes(
        rangemode='tozero',
        title_text='<b>% variance explained<b>',
        secondary_y=False
    )
    fig.update_yaxes(
        rangemode='tozero',
        title_text='<b># variants per window</b>',
        secondary_y=True
    )

    # adjust layout
    fig.update_layout(
        template='simple_white',
        font_family='Arial', font_color='black',
        autosize=False,
        width=(stop-start)/20000, height=500,
        xaxis=dict(ticks='outside', mirror=True, showline=True),
        yaxis=dict(ticks='outside', mirror=True, showline=True),
        legend={'traceorder':'normal'},
        title={'xanchor': 'center', 'y': 0.9, 'x': 0.45},
        hovermode='x unified',
    )

    return fig